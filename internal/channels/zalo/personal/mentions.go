package personal

import (
	"context"
	"log/slog"
	"strings"
	"unicode/utf16"

	"github.com/nextlevelbuilder/goclaw/internal/channels/zalo/personal/protocol"
)

var defaultBaselineContacts = map[string]string{
	"vinh lê":              "3004262889646691740",
	"ngô ngọc":             "5945359089887665583",
	"phùng văn luyện":      "4218136593749622436",
	"luyện phùng":          "4218136593749622436",
	"vương minh":           "3322195382887364919",
	"hồng hoàng":           "131714954850459646",
	"ngọc thuỷ":            "7929867505413189409",
	"ngọc thủy":            "7929867505413189409",
	"trang tran":           "7832478623954621343",
	"trúc thanh":           "3244794313129568042",
	"thị huyền":            "8027700215524395589",
	"khánh vàng":           "3809417504593405168",
	"lê quang cường":       "4389254476838983876",
	"phát":                 "2701418892740908368",
	"yến trang":            "3715698198122507965",
	"hoàng ngọc":           "2286546296357169558",
	"quangg":               "8323650366933171630",
	"nguyễn thị hồng vân":  "800492525149003062",
	"thanh quân":           "3666295940077903564",
	"như ý":                "4919547680453004392",
	"huy tran":             "2189151635201782348",
}

func removeDiacritics(s string) string {
	replacer := strings.NewReplacer(
		"à", "a", "á", "a", "ả", "a", "ã", "a", "ạ", "a",
		"ă", "a", "ằ", "a", "ắ", "a", "ẳ", "a", "ẵ", "a", "ặ", "a",
		"â", "a", "ầ", "a", "ấ", "a", "ẩ", "a", "ẫ", "a", "ậ", "a",
		"đ", "d",
		"è", "e", "é", "e", "ẻ", "e", "ẽ", "e", "ẹ", "e",
		"ê", "e", "ề", "e", "ế", "e", "ể", "e", "ễ", "e", "ệ", "e",
		"ì", "i", "í", "i", "ỉ", "i", "ĩ", "i", "ị", "i",
		"ò", "o", "ó", "o", "ỏ", "o", "õ", "o", "ọ", "o",
		"ô", "o", "ồ", "o", "ố", "o", "ổ", "o", "ỗ", "o", "ộ", "o",
		"ơ", "o", "ờ", "o", "ớ", "o", "ở", "o", "ỡ", "o", "ợ", "o",
		"ù", "u", "ú", "u", "ủ", "u", "ũ", "u", "ụ", "u",
		"ư", "u", "ừ", "u", "ứ", "u", "ử", "u", "ữ", "u", "ự", "u",
		"ỳ", "y", "ý", "y", "ỷ", "y", "ỹ", "y", "ỵ", "y",
	)
	return replacer.Replace(strings.ToLower(s))
}

var commonHonorificPrefixes = []string{
	"chú ", "chu ", "anh ", "bạn ", "ban ", "chị ", "chi ", "em ", "bác ", "bac ", "cô ", "co ",
}

func isWordBoundary(r rune) bool {
	return r == ' ' || r == ',' || r == '.' || r == ':' || r == '!' || r == '?' || r == '\n' || r == '\r' || r == '\t' || r == ';' || r == '(' || r == ')'
}

// RegisterContact registers a contact name mapping into the channel cache.
func (c *Channel) RegisterContact(name, uid string) {
	if name == "" || uid == "" {
		return
	}
	clean := strings.TrimSpace(strings.ToLower(name))
	c.contactRegistry.Store(clean, uid)

	noAccent := removeDiacritics(clean)
	if noAccent != clean {
		c.contactRegistry.Store(noAccent, uid)
	}
}

// initContactRegistry initializes the contact registry with default contacts.
func (c *Channel) initContactRegistry() {
	for name, uid := range defaultBaselineContacts {
		c.RegisterContact(name, uid)
	}
}

// SyncContactsFromFriends fetches the friend list from Zalo and caches them.
func (c *Channel) SyncContactsFromFriends(ctx context.Context) {
	sess := c.session()
	if sess == nil {
		return
	}
	friends, err := protocol.FetchFriends(ctx, sess)
	if err != nil {
		slog.Debug("zalo_personal: sync friends error (non-fatal)", "error", err)
		return
	}
	count := 0
	for _, f := range friends {
		if f.UserID != "" {
			if f.DisplayName != "" {
				c.RegisterContact(f.DisplayName, f.UserID)
				count++
			}
			if f.ZaloName != "" {
				c.RegisterContact(f.ZaloName, f.UserID)
			}
		}
	}
	slog.Info("zalo_personal: synced friends for mention matching", "count", count)
}

// ExtractMentions inspects outgoing group text and extracts Zalo TMention metadata.
func (c *Channel) ExtractMentions(text string) []*protocol.TMention {
	if text == "" {
		return nil
	}

	botUID := ""
	if sess := c.session(); sess != nil {
		botUID = sess.UID
	}

	runes := []rune(text)
	var mentions []*protocol.TMention

	for i := 0; i < len(runes); i++ {
		if runes[i] != '@' {
			continue
		}

		subRunes := runes[i+1:]
		if len(subRunes) == 0 {
			break
		}
		subStr := strings.ToLower(string(subRunes))

		// Check @all / @tat ca
		if strings.HasPrefix(subStr, "all") || strings.HasPrefix(subStr, "tất cả") || strings.HasPrefix(subStr, "tat ca") || strings.HasPrefix(subStr, "everyone") {
			matchRuneLen := 3
			if strings.HasPrefix(subStr, "tất cả") {
				matchRuneLen = len([]rune("tất cả"))
			} else if strings.HasPrefix(subStr, "tat ca") {
				matchRuneLen = len([]rune("tat ca"))
			} else if strings.HasPrefix(subStr, "everyone") {
				matchRuneLen = len([]rune("everyone"))
			}
			pos := len(utf16.Encode(runes[:i]))
			tLen := len(utf16.Encode(runes[i : i+1+matchRuneLen]))
			mentions = append(mentions, &protocol.TMention{
				UID:  protocol.MentionAllUID,
				Pos:  pos,
				Len:  tLen,
				Type: protocol.MentionAll,
			})
			i += matchRuneLen
			continue
		}

		// Search in contact registry
		var bestUID string
		var bestMatchRuneLen int

		c.contactRegistry.Range(func(key, val any) bool {
			name, ok1 := key.(string)
			uid, ok2 := val.(string)
			if !ok1 || !ok2 || uid == botUID || uid == "" {
				return true
			}

			// 1. Direct match: e.g. text is "@Vinh Lê..."
			if strings.HasPrefix(subStr, name) {
				runeL := len([]rune(name))
				// Ensure word boundary after name (punctuation, space, or end of string)
				if len(subRunes) == runeL || isWordBoundary(subRunes[runeL]) {
					if runeL > bestMatchRuneLen {
						bestMatchRuneLen = runeL
						bestUID = uid
					}
				}
			}

			// 2. Prefix match: e.g. text is "@Chú Vinh Lê..."
			for _, pref := range commonHonorificPrefixes {
				fullCand := pref + name
				if strings.HasPrefix(subStr, fullCand) {
					runeL := len([]rune(fullCand))
					if len(subRunes) == runeL || isWordBoundary(subRunes[runeL]) {
						if runeL > bestMatchRuneLen {
							bestMatchRuneLen = runeL
							bestUID = uid
						}
					}
				}
			}

			return true
		})

		if bestUID != "" {
			pos := len(utf16.Encode(runes[:i]))
			tLen := len(utf16.Encode(runes[i : i+1+bestMatchRuneLen]))
			mentions = append(mentions, &protocol.TMention{
				UID:  bestUID,
				Pos:  pos,
				Len:  tLen,
				Type: protocol.MentionEach,
			})
			slog.Info("zalo_personal: extracted native mention",
				"uid", bestUID,
				"pos", pos,
				"len", tLen,
				"tag", string(runes[i:i+1+bestMatchRuneLen]),
			)
			i += bestMatchRuneLen
		}
	}

	return mentions
}
