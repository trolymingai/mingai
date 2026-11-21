package main

import (
	"context"
	"database/sql"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"strings"
	"time"

	_ "github.com/lib/pq"
	"github.com/nextlevelbuilder/goclaw/internal/channels/zalo/personal/protocol"
)

func main() {
	db, err := sql.Open("postgres", "postgres://goclaw:cd7bc3ebe5d9b7aeda4af251ecdac47e@127.0.0.1:5434/goclaw?sslmode=disable")
	if err != nil {
		log.Fatalf("connect db: %v", err)
	}
	defer db.Close()

	var credsRaw []byte
	err = db.QueryRow("SELECT credentials FROM channel_instances WHERE name = 'zalo-ming-ai';").Scan(&credsRaw)
	if err != nil {
		log.Fatalf("query creds: %v", err)
	}

	var creds struct {
		IMEI      string                `json:"imei"`
		Cookie    *protocol.CookieUnion `json:"cookie"`
		UserAgent string                `json:"userAgent"`
		Language  *string               `json:"language,omitempty"`
	}
	if err := json.Unmarshal(credsRaw, &creds); err != nil {
		log.Fatalf("unmarshal creds: %v", err)
	}

	protoCred := &protocol.Credentials{
		IMEI:      creds.IMEI,
		Cookie:    creds.Cookie,
		UserAgent: creds.UserAgent,
		Language:  creds.Language,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	sess := protocol.NewSession()
	if err := protocol.LoginWithCredentials(ctx, sess, *protoCred); err != nil {
		log.Fatalf("login failed: %v", err)
	}
	fmt.Printf("Logged in as UID=%s, SecretKey len=%d\n", sess.UID, len(sess.SecretKey))

	// Group: Test Ming AI
	groupID := "552328793123364999"
	hongHoangUID := "131714954850459646"

	// Content
	text := "Xin chào @Hồng Hoàng , Ming AI đang kiểm tra tính năng tag tên chuẩn xác!"
	tag := "@Hồng Hoàng"
	pos := strings.Index(text, tag)
	tagLen := len([]rune(tag))

	fmt.Printf("Text: %s\nPos: %d, Len: %d\n", text, pos, tagLen)

	mentions := []map[string]any{
		{
			"pos":  pos,
			"len":  tagLen,
			"uid":  hongHoangUID,
			"type": 0,
		},
	}
	mentionsJSON, _ := json.Marshal(mentions)

	payload := map[string]any{
		"grid":        groupID,
		"message":     text,
		"mentionInfo": string(mentionsJSON),
		"clientId":    time.Now().UnixMilli(),
		"visibility":  0,
		"ttl":         0,
	}

	blob, _ := json.Marshal(payload)
	key, _ := base64.StdEncoding.DecodeString(sess.SecretKey)
	encData, err := protocol.EncodeAESCBC(key, string(blob), false)
	if err != nil {
		log.Fatalf("encrypt payload: %v", err)
	}

	baseURL := sess.LoginInfo.ZpwServiceMapV3.Group[0]
	endpoint := baseURL + "/api/group/mention?zpw_ver=694&zpw_type=30&nretry=0"

	form := strings.NewReader("params=" + url.QueryEscape(encData))
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, form)
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("User-Agent", sess.UserAgent)

	resp, err := sess.Client.Do(req)
	if err != nil {
		log.Fatalf("do req: %v", err)
	}
	defer resp.Body.Close()

	var envelope protocol.Response[*string]
	json.NewDecoder(resp.Body).Decode(&envelope)
	fmt.Printf("Envelope: ErrorCode=%d, ErrorMsg=%s\n", envelope.ErrorCode, envelope.ErrorMessage)
	if envelope.Data != nil {
		fmt.Printf("Data encrypted len=%d\n", len(*envelope.Data))
	}
}
