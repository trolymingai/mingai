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

	// Fast-path: When staff/user in DM sends a sticker, icon/emoji, or casual social acknowledgment/courtesy,
	// react with heart (thả tim) to confirm receipt and do NOT spam text reply.
	isSticker := msg.Data.MsgType == "chat.sticker"
	isEmoji := isOnlyEmojiOrSticker(content)
	if isSticker || isEmoji || isSocialAckOrPleasantry(content) {
		slog.Info("zalo_personal: received sticker/emoji/ack in DM, sending heart reaction and muting text reply",
			"sender", senderID,
			"msg_id", msg.Data.MsgID,
		)
		sess := c.session()
		if sess != nil {
			_ = protocol.SendReaction(ctx, sess, threadID, protocol.ThreadTypeUser, msg.Data.MsgID, msg.Data.GetCliMsgID(), "/-heart", 5)
		}
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

	// Step 2: @mention gating — in group chats, Ming AI MUST ONLY respond when explicitly tagged or mentioned!
	// We check both official Zalo mention tag (m.UID == botUID) and plaintext tag (@Ming, @Troly Ming, etc.)
	// Special Case: Auto-catch all messages in "Ming|Báo sự cố" (threadID: 2785144727994011019) without requiring @mention
	isIncidentGroup := (threadID == "2785144727994011019")
	wasMentioned := c.checkBotMentioned(msg.Data.Mentions) || isBotMentionedInText(content) || isIncidentGroup
	if c.RequireMention() && !wasMentioned {
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

	// Step 2b: Zero-Reply filter for social acks / courtesies even when tagged.
	// If the message only consists of casual pleasantries (e.g., "@Ming AI ok", "@Ming AI cảm ơn", "@Ming AI dạ"),
	// react with heart to silently confirm receipt without spamming the group chat with useless text.
	strippedContent := stripBotMentions(content)
	if isSocialAckOrPleasantry(strippedContent) || isOnlyEmojiOrSticker(strippedContent) {
		slog.Info("zalo_personal: received social ack/pleasantry with mention in group, sending heart reaction and muting text reply",
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

	// Requirement 4: Detect new member self-introduction in group (only applied when bot is mentioned/tagged)
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
	if att == nil {
		return "", nil
	}
	fileURL := att.GetURL()
	if fileURL == "" {
		if text := content.AttachmentText(); text != "" {
			return text, nil
		}
		return "", nil
	}

	// Download the attachment file.
	filePath, err := downloadFile(context.Background(), fileURL)
	if err != nil {
		slog.Warn("zalo_personal: failed to download attachment", "url", fileURL, "error", err)
		if text := content.AttachmentText(); text != "" {
			return text, nil
		}
		return "", nil
	}

	// Detect MIME type via content sniffing (first 512 bytes) with fallback to extension
	mimeType := detectFileMIME(filePath)
	mediaKind := media.MediaKindFromMime(mimeType)

	if mediaKind != media.TypeImage && att.IsImage() {
		mediaKind = media.TypeImage
		if !strings.HasPrefix(mimeType, "image/") {
			mimeType = "image/jpeg"
		}
	}
	if mediaKind != media.TypeVideo && att.IsVideo() {
		mediaKind = media.TypeVideo
		if !strings.HasPrefix(mimeType, "video/") {
			mimeType = "video/mp4"
		}
	}

	title := att.GetTitle()

	// Build the <media:*> tag that the agent loop's enrichImageIDs/enrichMediaIDs expects.
	tag := media.BuildMediaTags([]media.MediaInfo{{
		Type:        mediaKind,
		FilePath:    filePath,
		ContentType: mimeType,
		FileName:    title,
	}})

	if title != "" && title != filepath.Base(filePath) {
		return fmt.Sprintf("%s\n%s", title, tag), []string{filePath}
	}
	return tag, []string{filePath}
}

func detectFileMIME(filePath string) string {
	f, err := os.Open(filePath)
	if err == nil {
		buf := make([]byte, 512)
		n, _ := f.Read(buf)
		f.Close()
		if n > 0 {
			detected := http.DetectContentType(buf[:n])
			if detected != "application/octet-stream" {
				return detected
			}
		}
	}
	return media.DetectMIMEType(filePath)
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
		lowerURL := strings.ToLower(fileURL)
		if strings.Contains(lowerURL, "/jpg/") || strings.Contains(lowerURL, "/jpeg/") {
			ext = ".jpg"
		} else if strings.Contains(lowerURL, "/png/") {
			ext = ".png"
		} else if strings.Contains(lowerURL, "/gif/") {
			ext = ".gif"
		} else if strings.Contains(lowerURL, "/webp/") {
			ext = ".webp"
		} else if strings.Contains(lowerURL, "/video/") || strings.Contains(lowerURL, "/mp4/") {
			ext = ".mp4"
		} else {
			ext = ".bin"
		}
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


// isBotMentionedInText checks if the bot is explicitly tagged or mentioned in the message text.
// Requires explicit '@' prefix or targeted bot summon phrase.
func isBotMentionedInText(content string) bool {
	lower := strings.ToLower(content)
	tagKeywords := []string{
		"@ming",
		"@troly ming",
		"@trợ lý ming",
		"@trolyming",
		"@trợlýming",
		"@ming ai",
		"@mingai",
		"@ming coffee",
		"@ming coffee roastery",
		"@mingcoffeeroastery",
		"@troly",
		"@trợ lý",
		"@bot",
		"trợ lý ming ơi",
		"tro ly ming oi",
		"ming ơi",
		"ming oi",
		"ming ai ơi",
		"ming ai oi",
	}
	for _, kw := range tagKeywords {
		if strings.Contains(lower, kw) {
			return true
		}
	}
	return false
}

// stripBotMentions removes known bot mention triggers from the text so we can inspect the core message.
func stripBotMentions(content string) string {
	res := content
	lowerTriggers := []string{
		"@troly ming",
		"@trợ lý ming",
		"@trolyming",
		"@trợlýming",
		"@ming ai",
		"@mingai",
		"@ming",
		"@troly",
		"@trợ lý",
		"@bot",
		"trợ lý ming ơi",
		"tro ly ming oi",
		"ming ơi",
		"ming oi",
		"ming ai ơi",
		"ming ai oi",
	}
	for _, trigger := range lowerTriggers {
		for {
			idx := strings.Index(strings.ToLower(res), trigger)
			if idx == -1 {
				break
			}
			res = res[:idx] + res[idx+len(trigger):]
		}
	}
	return strings.TrimSpace(res)
}

// isSocialAckOrPleasantry checks if a message is purely a conversational acknowledgment,
// greeting, or courtesy with zero operational action required.
func isSocialAckOrPleasantry(text string) bool {
	trimmed := strings.TrimSpace(text)
	if trimmed == "" {
		return true // Empty message (e.g. only tagged bot)
	}

	// Normalize: lower case and strip standard punctuation
	normalized := strings.ToLower(trimmed)
	normalized = strings.Trim(normalized, " .,:;!?'\"`~*#-_()[]{}<>/\\")

	// If after stripping punctuation it's empty, treat as pure filler
	if normalized == "" {
		return true
	}

	// Exact matches for pure acknowledgments and courtesies
	ackWords := map[string]bool{
		// Affirmations / ACK
		"da": true, "dạ": true,
		"vang": true, "vâng": true,
		"da vang": true, "dạ vâng": true,
		"da vang a": true, "dạ vâng ạ": true,
		"vang a": true, "vâng ạ": true,
		"da a": true, "dạ a": true,
		"da anh": true, "dạ anh": true,
		"da c": true, "dạ c": true,
		"da chi": true, "dạ chị": true,
		"da em biet": true, "dạ em biết": true,
		"da em biet roi": true, "dạ em biết rồi": true,
		"em biet roi": true, "em biết rồi": true,
		"da e biet roi": true, "dạ e biết rồi": true,
		"da ro": true, "dạ rõ": true,
		"ro": true, "rõ": true,
		"da em ro": true, "dạ em rõ": true,
		"da e ro": true, "dạ e rõ": true,
		"da em hieu": true, "dạ em hiểu": true,
		"em hieu roi": true, "em hiểu rồi": true,
		"da hieu": true, "dạ hiểu": true,
		"da nhan": true, "dạ nhận": true,
		"da nhan duoc": true, "dạ nhận được": true,
		"da nhan roi": true, "dạ nhận rồi": true,
		"em nhan roi": true, "em nhận rồi": true,
		"da e nhan roi": true, "dạ e nhận rồi": true,
		"e nhan roi": true, "e nhận rồi": true,
		"da nhan thong tin": true, "dạ nhận thông tin": true,
		"da e ro a": true, "dạ e rõ ạ": true,
		"da e hieu roi a": true, "dạ e hiểu rồi ạ": true,
		"ok": true, "oke": true, "oki": true, "okie": true,
		"ok a": true, "ok em": true, "ok anh": true,
		"ok c": true, "ok chi": true, "ok chị": true,
		"ok nhe": true, "ok nhé": true, "ok nha": true,
		"oke nha": true, "oki nha": true, "ok r": true,
		"ok roi": true, "ok rồi": true, "ok luon": true, "ok luôn": true,
		"ok b": true, "ok bạn": true, "ok ban": true,
		"da em cam on": true, "dạ em cảm ơn": true,
		"da cam on": true, "dạ cảm ơn": true,
		"cam on": true, "cảm ơn": true,
		"cam on nha": true, "cảm ơn nha": true,
		"cam on nhe": true, "cảm ơn nhé": true,
		"cam on a": true, "cảm ơn a": true,
		"cam on anh": true, "cảm ơn anh": true,
		"cam on c": true, "cảm ơn c": true,
		"cam on chi": true, "cảm ơn chị": true,
		"cam on nhieu": true, "cảm ơn nhiều": true,
		"tks": true, "thanks": true, "thank you": true, "ty": true, "thank": true,
		"thank kiu": true, "thx": true,
		// Greetings / Social
		"chao": true, "chào": true,
		"chao a": true, "chào a": true,
		"chao anh": true, "chào anh": true,
		"chao em": true, "chào em": true,
		"chao ca nha": true, "chào cả nhà": true,
		"hi": true, "hello": true, "helo": true, "alo": true,
		"haha": true, "hahaha": true, "hihi": true, "hihihi": true,
		"hehe": true, "hehehe": true, "hjhj": true, "kaka": true, "keke": true,
		"ngu ngon": true, "ngủ ngon": true,
		"chuc ngu ngon": true, "chúc ngủ ngon": true,
		"bye": true, "good night": true, "g9": true,
	}

	return ackWords[normalized]
}
