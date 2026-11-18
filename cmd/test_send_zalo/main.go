package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"time"

	_ "github.com/lib/pq"
	"github.com/nextlevelbuilder/goclaw/internal/channels/zalo/personal/protocol"
)

func main() {
	db, err := sql.Open("postgres", "postgres://goclaw:cd7bc3ebe5d9b7aeda4af251ecdac47e@172.18.0.1:5434/goclaw?sslmode=disable")
	if err != nil {
		log.Fatalf("db open: %v", err)
	}
	defer db.Close()

	var credsJSON string
	err = db.QueryRow("SELECT credentials FROM channel_instances WHERE name = 'zalo-ming-ai'").Scan(&credsJSON)
	if err != nil {
		log.Fatalf("query creds: %v", err)
	}

	var cred protocol.Credentials
	if err := json.Unmarshal([]byte(credsJSON), &cred); err != nil {
		log.Fatalf("unmarshal creds: %v", err)
	}

	sess := protocol.NewSession()
	ctx, cancel := context.WithTimeout(context.Background(), 25*time.Second)
	defer cancel()

	if err := protocol.LoginWithCredentials(ctx, sess, cred); err != nil {
		log.Fatalf("LoginWithCredentials failed: %v", err)
	}

	groupID := "552328793123364999" // Test Ming AI
	msg := `🌅 Chào bạn Hồng Hoàng và ca làm việc Test Ming AI! ✨

Ming gửi bạn bảng Checklist Vận Hành Đầu Ca trực tuyến trên Odoo ERP:
📲 https://erp.mingcoffeemore.com/my/tasks/94?access_token=8e044212-6e0e-4563-afcf-f17c6d39ae23

Bạn có thể bấm vào link xem và tick trực tiếp trên điện thoại, hoặc nhắn nhanh vào nhóm:
"Ming ơi, mở ca xong, tủ mát 3.5 độ, nồi hơi 1.2 bar" để Ming tự động ghi nhận nhé! Chúc bạn ca làm thật chú tâm và nhiều niềm vui! ☕`

	msgID, err := protocol.SendMessage(ctx, sess, groupID, protocol.ThreadTypeGroup, msg)
	if err != nil {
		log.Fatalf("SendMessage failed: %v", err)
	}

	fmt.Printf("SUCCESS: Sent message to group Test Ming AI, msgID=%s\n", msgID)
}
