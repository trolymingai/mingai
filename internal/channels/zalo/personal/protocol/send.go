package protocol

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"time"
)

// SendMessage sends a text message to a user or group without mentions.
func SendMessage(ctx context.Context, sess *Session, threadID string, threadType ThreadType, text string) (string, error) {
	return SendMessageWithMentions(ctx, sess, threadID, threadType, text, nil)
}

// SendMessageWithMentions sends a text message to a user or group with optional mentions.
// threadID: user UID (DM) or group ID (group).
func SendMessageWithMentions(ctx context.Context, sess *Session, threadID string, threadType ThreadType, text string, mentions []*TMention) (string, error) {
	if text == "" {
		return "", fmt.Errorf("zalo_personal: message text cannot be empty")
	}

	serviceKey := "chat"
	apiPath := "/api/message/sms"
	if threadType == ThreadTypeGroup {
		serviceKey = "group"
		if len(mentions) > 0 {
			apiPath = "/api/group/mention"
		} else {
			apiPath = "/api/group/sendmsg"
		}
	}

	baseURL := getServiceURL(sess, serviceKey)
	if baseURL == "" {
		return "", fmt.Errorf("zalo_personal: no service URL for %s", serviceKey)
	}

	// Build payload
	payload := map[string]any{
		"message":  text,
		"clientId": time.Now().UnixMilli(),
		"ttl":      0,
	}
	if threadType == ThreadTypeGroup {
		payload["grid"] = threadID
		payload["visibility"] = 0
		if len(mentions) > 0 {
			mentionJSON, _ := json.Marshal(mentions)
			payload["mentionInfo"] = string(mentionJSON)
			payload["mentions"] = mentions
		}
	} else {
		payload["toid"] = threadID
		payload["imei"] = sess.IMEI
	}

	// Encrypt payload with session secret key
	encData, err := encryptPayload(sess, payload)
	if err != nil {
		return "", fmt.Errorf("zalo_personal: encrypt send payload: %w", err)
	}

	// Build URL with standard params
	sendURL := makeURL(sess, baseURL+apiPath, map[string]any{"nretry": 0}, true)

	// POST form-encoded
	form := buildFormBody(map[string]string{"params": encData})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, sendURL, form)
	if err != nil {
		return "", err
	}
	setDefaultHeaders(req, sess)

	resp, err := sess.Client.Do(req)
	if err != nil {
		return "", fmt.Errorf("zalo_personal: send message: %w", err)
	}
	defer resp.Body.Close()

	// Send response is encrypted: {"error_code":0, "data":"<encrypted>"}
	var envelope Response[*string]
	if err := readJSON(resp, &envelope); err != nil {
		return "", fmt.Errorf("zalo_personal: parse send response: %w", err)
	}
	if envelope.ErrorCode != 0 {
		return "", fmt.Errorf("zalo_personal: send error code %d", envelope.ErrorCode)
	}
	if envelope.Data == nil {
		return "", nil
	}

	plain, err := decryptDataField(sess, *envelope.Data)
	if err != nil {
		return "", fmt.Errorf("zalo_personal: decrypt send response: %w", err)
	}

	var result map[string]any
	if err := json.Unmarshal(plain, &result); err != nil {
		return string(plain), nil
	}
	if msgID, ok := result["msgId"]; ok {
		return fmt.Sprintf("%v", msgID), nil
	}
	return string(plain), nil
}

// SendTypingEvent sends a typing indicator to a user or group.
// Zalo typing lasts ~5s server-side; callers should re-send every 3-4s.
func SendTypingEvent(ctx context.Context, sess *Session, threadID string, threadType ThreadType) error {
	serviceKey := "chat"
	apiPath := "/api/message/typing"
	if threadType == ThreadTypeGroup {
		serviceKey = "group"
		apiPath = "/api/group/typing"
	}

	baseURL := getServiceURL(sess, serviceKey)
	if baseURL == "" {
		return fmt.Errorf("zalo_personal: no service URL for %s", serviceKey)
	}

	payload := map[string]any{"imei": sess.IMEI}
	if threadType == ThreadTypeGroup {
		payload["grid"] = threadID
	} else {
		payload["toid"] = threadID
		payload["destType"] = 3 // DestTypeUser
	}

	encData, err := encryptPayload(sess, payload)
	if err != nil {
		return fmt.Errorf("zalo_personal: encrypt typing payload: %w", err)
	}

	typingURL := makeURL(sess, baseURL+apiPath, nil, true)
	form := buildFormBody(map[string]string{"params": encData})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, typingURL, form)
	if err != nil {
		return err
	}
	setDefaultHeaders(req, sess)

	resp, err := sess.Client.Do(req)
	if err != nil {
		return fmt.Errorf("zalo_personal: send typing: %w", err)
	}
	defer resp.Body.Close()

	var envelope Response[any]
	if err := readJSON(resp, &envelope); err != nil {
		return fmt.Errorf("zalo_personal: parse typing response: %w", err)
	}
	if envelope.ErrorCode != 0 {
		return fmt.Errorf("zalo_personal: typing error code %d", envelope.ErrorCode)
	}
	return nil
}

// getServiceURL extracts a service base URL from LoginInfo.
func getServiceURL(sess *Session, service string) string {
	if sess.LoginInfo == nil {
		return ""
	}
	var urls []string
	switch service {
	case "chat":
		urls = sess.LoginInfo.ZpwServiceMapV3.Chat
	case "group":
		urls = sess.LoginInfo.ZpwServiceMapV3.Group
	case "file":
		urls = sess.LoginInfo.ZpwServiceMapV3.File
	case "profile":
		urls = sess.LoginInfo.ZpwServiceMapV3.Profile
	case "group_poll":
		urls = sess.LoginInfo.ZpwServiceMapV3.GroupPoll
	case "reaction":
		urls = sess.LoginInfo.ZpwServiceMapV3.Reaction
		if len(urls) == 0 {
			urls = sess.LoginInfo.ZpwServiceMapV3.Chat
		}
	case "friend":
		urls = sess.LoginInfo.ZpwServiceMapV3.Friend
		if len(urls) == 0 {
			urls = sess.LoginInfo.ZpwServiceMapV3.Profile
		}
	}
	if len(urls) == 0 {
		return ""
	}
	return urls[0]
}

// encryptPayload encrypts a JSON payload with the session's secret key via AES-CBC.
func encryptPayload(sess *Session, payload map[string]any) (string, error) {
	blob, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	key, err := base64.StdEncoding.DecodeString(sess.SecretKey)
	if err != nil {
		return "", fmt.Errorf("decode secret key: %w", err)
	}
	return EncodeAESCBC(key, string(blob), false)
}

// SendReaction sends a reaction (e.g. heart "/-heart" with rType=5) to a message in group or DM.
func SendReaction(ctx context.Context, sess *Session, threadID string, threadType ThreadType, msgID string, cliMsgID string, icon string, rType int) error {
	baseURL := getServiceURL(sess, "reaction")
	if baseURL == "" {
		return fmt.Errorf("zalo_personal: no reaction service URL")
	}

	apiPath := "/api/message/reaction"
	if threadType == ThreadTypeGroup {
		apiPath = "/api/group/reaction"
	}

	gMsgID, _ := strconv.ParseInt(msgID, 10, 64)
	cMsgID, _ := strconv.ParseInt(cliMsgID, 10, 64)
	if cMsgID == 0 {
		cMsgID = time.Now().UnixMilli()
	}

	detail := map[string]any{
		"rMsg": []map[string]any{
			{
				"gMsgID":  gMsgID,
				"cMsgID":  cMsgID,
				"msgType": 1,
			},
		},
		"rIcon":  icon,
		"rType":  rType,
		"source": 6,
	}
	detailJSON, err := json.Marshal(detail)
	if err != nil {
		return err
	}

	params := map[string]any{
		"react_list": []map[string]any{
			{
				"message":  string(detailJSON),
				"clientId": time.Now().UnixMilli(),
			},
		},
	}
	if threadType == ThreadTypeGroup {
		params["grid"] = threadID
		params["imei"] = sess.IMEI
	} else {
		params["toid"] = threadID
	}

	encData, err := encryptPayload(sess, params)
	if err != nil {
		return fmt.Errorf("zalo_personal: encrypt reaction: %w", err)
	}

	reactURL := makeURL(sess, baseURL+apiPath, nil, true)
	form := buildFormBody(map[string]string{"params": encData})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, reactURL, form)
	if err != nil {
		return err
	}
	setDefaultHeaders(req, sess)

	resp, err := sess.Client.Do(req)
	if err != nil {
		return fmt.Errorf("zalo_personal: send reaction: %w", err)
	}
	defer resp.Body.Close()

	var envelope Response[any]
	if err := readJSON(resp, &envelope); err != nil {
		return fmt.Errorf("zalo_personal: parse reaction response: %w", err)
	}
	if envelope.ErrorCode != 0 {
		return fmt.Errorf("zalo_personal: reaction error %d: %s", envelope.ErrorCode, envelope.ErrorMessage)
	}
	return nil
}
