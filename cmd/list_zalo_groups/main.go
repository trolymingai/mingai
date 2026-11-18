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

	groups, err := protocol.FetchGroups(ctx, sess)
	if err != nil {
		log.Fatalf("fetch groups failed: %v", err)
	}

	fmt.Println("=== ALL ZALO GROUPS ===")
	for i, g := range groups {
		fmt.Printf("[%d] GroupID: %s | Name: %s | Members: %d\n", i+1, g.GroupID, g.Name, g.TotalMember)
	}
}
