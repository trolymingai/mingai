package personal

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
	"unicode"

	"github.com/nextlevelbuilder/goclaw/internal/channels"
	"github.com/nextlevelbuilder/goclaw/internal/channels/media"
	"github.com/nextlevelbuilder/goclaw/internal/channels/typing"
	"github.com/nextlevelbuilder/goclaw/internal/channels/zalo/personal/protocol"
	"github.com/nextlevelbuilder/goclaw/internal/store"
	"github.com/nextlevelbuilder/goclaw/internal/tools"
)

func (c *Channel) handleMessage(msg protocol.Message) {
	if msg.IsSelf() {
		return
	}

	switch m := msg.(type) {
	case protocol.UserMessage:
		c.handleDM(m)
	case protocol.GroupMessage:
		c.handleGroupMessage(m)
	}
}

func (c *Channel) handleDM(msg protocol.UserMessage) {
	ctx := context.Background()
	ctx = store.WithTenantID(ctx, c.TenantID())
	senderID := msg.Data.UIDFrom
	threadID := msg.ThreadID()

	content, media := extractContentAndMedia(msg.Data.Content)
	if content == "" {
		return
	}

	if !c.checkDMPolicy(ctx, senderID, threadID) {
		return
	}

	// Annotate with sender display name so the agent knows who is messaging.
	senderName := msg.Data.DName
	if senderName != "" {
		content = fmt.Sprintf("[From: %s]\n%s", senderName, content)
	}

	slog.Debug("zalo_personal DM received",
		"sender", senderID,
		"dname", senderName,
		"thread", threadID,
		"preview", channels.Truncate(content, 50),
	)

	c.startTyping(threadID, protocol.ThreadTypeUser)

	// Collect contact for DM messages.
	if cc := c.ContactCollector(); cc != nil {
		cc.EnsureContact(ctx, c.Type(), c.Name(), senderID, senderID, senderName, "", "direct", "user", "", "")
	}

	metadata := map[string]string{
		"message_id":   msg.Data.MsgID,
		"platform":     channels.TypeZaloPersonal,
		"display_name": channels.SanitizeDisplayName(senderName),
	}
	c.HandleMessage(senderID, threadID, content, media, metadata, "direct")
}

func (c *Channel) handleGroupMessage(msg protocol.GroupMessage) {
	ctx := context.Background()
	ctx = store.WithTenantID(ctx, c.TenantID())
	senderID := msg.Data.UIDFrom
	threadID := msg.ThreadID()

	content, media := extractContentAndMedia(msg.Data.Content)
	if content == "" {
		return
	}

	// Step 1: enforce access policy (allowlist/pairing). Hard reject — don't record history.
	if !c.checkGroupPolicy(ctx, senderID, threadID) {
		return
	}

	senderName := msg.Data.DName
	if senderName == "" {
		senderName = senderID
	}

	// Requirement 1: When staff in a group chat sends a sticker or icon/emoji,
	// Ming AI MUST only react with heart (thả tim) and NOT reply with any text!
	isSticker := msg.Data.MsgType == "chat.sticker"
	isEmoji := isOnlyEmojiOrSticker(content)
	if isSticker || isEmoji {
		slog.Info("zalo_personal: received sticker/emoji in group, sending heart reaction and muting text reply",
			"group_id", threadID,
			"sender", senderName,
			"msg_id", msg.Data.MsgID,
		)
		sess := c.session()
		if sess != nil {
			_ = protocol.SendReaction(ctx, sess, threadID, protocol.ThreadTypeGroup, msg.Data.MsgID, msg.Data.GetCliMsgID(), "/-heart", 5)
		}
		return // Do not forward to agent loop, zero text reply
	}

	// Requirement 4: Detect new member self-introduction in group
	lowerContent := strings.ToLower(content)
	isIntro := false
	introKeywords := []string{
		"chào mọi người em là", "chào cả nhà em là", "chào mọi người mình là", "chào cả nhà mình là",
		"em là nhân viên mới", "mình là nhân viên mới", "em là barista mới", "em là thu ngân mới",
		"em là phục vụ mới", "mình là barista mới", "mình là thu ngân mới", "em mới vào làm",
		"mình mới vào làm", "thành viên mới", "nhân sự mới", "xin chào mọi người em tên",
		"xin chào cả nhà em tên", "em xin phép giới thiệu", "mình xin phép giới thiệu",
	}
	for _, kw := range introKeywords {
		if strings.Contains(lowerContent, kw) {
			isIntro = true
			break
		}
	}
	if isIntro {
		content = "[THÀNH VIÊN MỚI GIỚI THIỆU BẢN THÂN]\n" + content + "\n\n(Chỉ dẫn Ming AI: Hãy gửi lời chào đón ấm áp, chân thành gia nhập đại gia đình Ming Coffee, lan tỏa giá trị cốt lõi Tử Tế & Chú Tâm, và hướng dẫn họ: 'Để làm việc, giao việc, kiểm tra checklist hoặc tra cứu quy trình, bạn chỉ cần tag @Ming AI trong nhóm hoặc nhắn tin riêng cho Ming nhé!')"
	}

	// Step 2: @mention gating — record non-mentioned messages in history and return.
	if c.RequireMention() {
		wasMentioned := c.checkBotMentioned(msg.Data.Mentions)
		if !wasMentioned {
			c.GroupHistory().Record(threadID, channels.HistoryEntry{
				Sender:    senderName,
				SenderID:  senderID,
				Body:      content,
				Media:     media,
				Timestamp: time.Now(),
				MessageID: msg.Data.MsgID,
			}, c.HistoryLimit())

			// Collect contact even when bot is not mentioned (cache prevents DB spam).
			if cc := c.ContactCollector(); cc != nil {
				cc.EnsureContact(ctx, c.Type(), c.Name(), senderID, senderID, senderName, "", "group", "user", "", "")
			}

			slog.Debug("zalo_personal group message recorded (no mention)",
				"group_id", threadID,
				"sender", senderName,
			)
			return
		}
	}

	slog.Debug("zalo_personal group message received",
		"sender", senderID,
		"group", threadID,
		"preview", channels.Truncate(content, 50),
	)

	// Step 3: flush pending history + annotate current message with group name and sender name.
	groupName := c.GetGroupName(ctx, threadID)
	var annotated string
	if groupName != "" {
		annotated = fmt.Sprintf("[Nhóm: %s | Người gửi: %s]\n%s", groupName, senderName, content)
	} else {
		annotated = fmt.Sprintf("[From: %s]\n%s", senderName, content)
	}
	finalContent := annotated
	if c.HistoryLimit() > 0 {
		finalContent = c.GroupHistory().BuildContext(threadID, annotated, c.HistoryLimit())
	}

	c.startTyping(threadID, protocol.ThreadTypeGroup)

	// Collect media from pending history entries (images sent before this @mention).
	// Must come after BuildContext — CollectMedia nulls out Media fields to prevent double-cleanup.
	histMedia := c.GroupHistory().CollectMedia(threadID)
	allMedia := append(histMedia, media...)

	// Collect contact for group-mentioned messages.
	if cc := c.ContactCollector(); cc != nil {
		cc.EnsureContact(ctx, c.Type(), c.Name(), senderID, senderID, senderName, "", "group", "user", "", "")
	}

	metadata := map[string]string{
		"message_id":   msg.Data.MsgID,
		"platform":     channels.TypeZaloPersonal,
		"group_id":     threadID,
		"group_name":   groupName,
		"display_name": channels.SanitizeDisplayName(senderName),
	}
	c.HandleMessage(senderID, threadID, finalContent, allMedia, metadata, "group")

	// Clear pending history after sending to agent (matches Telegram/Discord/Slack/Feishu pattern).
	c.GroupHistory().Clear(threadID)
}

// startTyping starts a typing indicator with keepalive for the given thread.
// Zalo typing expires after ~5s, so keepalive fires every 3s.
func (c *Channel) startTyping(threadID string, threadType protocol.ThreadType) {
	sess := c.session()
	ctrl := typing.New(typing.Options{
		MaxDuration:       60 * time.Second,
		KeepaliveInterval: 4 * time.Second,
		StartFn: func() error {
			return protocol.SendTypingEvent(context.Background(), sess, threadID, threadType)
		},
	})
	if prev, ok := c.typingCtrls.Load(threadID); ok {
		if ctrl, ok := prev.(*typing.Controller); ok {
			ctrl.Stop()
		}
	}
	c.typingCtrls.Store(threadID, ctrl)
	ctrl.Start()
}

// extractContentAndMedia returns text content (with <media:*> tags) and optional local media
// file paths from a Zalo message. For text messages, media is nil. For attachments, the file
// is downloaded and classified by MIME type, matching the pattern used by Telegram/Discord/Feishu.
func extractContentAndMedia(content protocol.Content) (string, []string) {
	if text := content.Text(); text != "" {
		return text, nil
	}
	att := content.ParseAttachment()
	if att == nil || att.Href == "" {
		return "", nil
	}

	// Download the attachment file.
	filePath, err := downloadFile(context.Background(), att.Href)
	if err != nil {
		slog.Warn("zalo_personal: failed to download attachment", "url", att.Href, "error", err)
		// Return human-readable fallback so the message isn't silently dropped.
		if text := content.AttachmentText(); text != "" {
			return text, nil
		}
		return "", nil
	}

	// Classify by MIME type (image, video, audio, document) — same as Discord/Feishu.
	mimeType := media.DetectMIMEType(filePath)
	mediaKind := media.MediaKindFromMime(mimeType)

	// For images, also check via Zalo CDN path patterns (e.g. /jpg/, /png/) since
	// temp files lose the original extension context.
	if mediaKind != media.TypeImage && att.IsImage() {
		mediaKind = media.TypeImage
	}

	// Build the <media:*> tag that the agent loop's enrichImageIDs/enrichMediaIDs expects.
	tag := media.BuildMediaTags([]media.MediaInfo{{
		Type:        mediaKind,
		FilePath:    filePath,
		ContentType: mimeType,
		FileName:    att.Title,
	}})

	return tag, []string{filePath}
}

const maxMediaBytes = 20 * 1024 * 1024 // 20MB (matches Telegram default)

// downloadFile downloads a URL to a temp file and returns the local path.
// Validates against SSRF and enforces timeout and size limits.
func downloadFile(ctx context.Context, fileURL string) (string, error) {
	if err := tools.CheckSSRF(fileURL); err != nil {
		return "", fmt.Errorf("ssrf check: %w", err)
	}

	client := &http.Client{Timeout: 30 * time.Second}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, fileURL, nil)
	if err != nil {
		return "", fmt.Errorf("download: %w", err)
	}
	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("download: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("download status %d", resp.StatusCode)
	}

	// Strip query params before extracting extension.
	path := fileURL
	if i := strings.IndexByte(path, '?'); i >= 0 {
		path = path[:i]
	}
	ext := filepath.Ext(path)
	if ext == "" || len(ext) > 5 {
		ext = ".bin"
	}

	tmpFile, err := os.CreateTemp("", "goclaw_zca_*"+ext)
	if err != nil {
		return "", fmt.Errorf("create temp: %w", err)
	}
	defer tmpFile.Close()

	written, err := io.Copy(tmpFile, io.LimitReader(resp.Body, maxMediaBytes+1))
	if err != nil {
		os.Remove(tmpFile.Name())
		return "", fmt.Errorf("save: %w", err)
	}
	if written > maxMediaBytes {
		os.Remove(tmpFile.Name())
		return "", fmt.Errorf("file too large: %d bytes (max %d)", written, maxMediaBytes)
	}

	return tmpFile.Name(), nil
}

// isOnlyEmojiOrSticker reports true if the string is made exclusively of emojis, icons, and whitespace.
func isOnlyEmojiOrSticker(text string) bool {
	trimmed := strings.TrimSpace(text)
	if trimmed == "" {
		return false
	}
	hasRune := false
	for _, r := range trimmed {
		if unicode.IsSpace(r) {
			continue
		}
		hasRune = true
		isEmoji := (r >= 0x1F600 && r <= 0x1F64F) || // Emoticons
			(r >= 0x1F300 && r <= 0x1F5FF) || // Misc Symbols and Pictographs
			(r >= 0x1F680 && r <= 0x1F6FF) || // Transport and Map
			(r >= 0x1F900 && r <= 0x1F9FF) || // Supplemental Symbols and Pictographs
			(r >= 0x1FA00 && r <= 0x1FAFF) || // Symbols and Pictographs Extended-A
			(r >= 0x2600 && r <= 0x26FF) ||   // Misc Symbols
			(r >= 0x2700 && r <= 0x27BF) ||   // Dingbats
			(r >= 0xFE00 && r <= 0xFE0F) ||   // Variation Selectors
			(r == 0x200D) ||                   // Zero Width Joiner
			(r >= 0x2300 && r <= 0x23FF) ||   // Misc Technical
			(r >= 0x2B50 && r <= 0x2B55) ||   // Stars
			(r >= 0x203C && r <= 0x2049) ||   // Punctuation Emojis
			(r >= 0x2194 && r <= 0x21AA) ||   // Arrows
			(r >= 0x2934 && r <= 0x2935)
		if !isEmoji {
			return false
		}
	}
	return hasRune
}
