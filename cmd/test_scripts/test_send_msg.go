package main

import (
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/gorilla/websocket"
)

type Frame struct {
	Type   string         `json:"type"`
	ID     string         `json:"id,omitempty"`
	Method string         `json:"method,omitempty"`
	Params map[string]any `json:"params,omitempty"`
	Result any            `json:"result,omitempty"`
	Error  any            `json:"error,omitempty"`
}

func main() {
	header := http.Header{}
	c, _, err := websocket.DefaultDialer.Dial("ws://127.0.0.1:18790/ws", header)
	if err != nil {
		log.Fatalf("dial: %v", err)
	}
	defer c.Close()

	// 1. Connect
	connectReq := Frame{
		Type:   "req",
		ID:     "c1",
		Method: "connect",
		Params: map[string]any{
			"token":   "eae9134b7b6014847a75303456605872",
			"user_id": "system",
		},
	}
	c.WriteJSON(connectReq)
	var connectResp Frame
	c.ReadJSON(&connectResp)
	fmt.Printf("Connect: %+v\n", connectResp)

	// Send test to Test Ming AI group (552328793123364999)
	sendReq := Frame{
		Type:   "req",
		ID:     "s1",
		Method: "send",
		Params: map[string]any{
			"channel": "zalo-ming-ai",
			"to":      "552328793123364999",
			"message": "Kiểm tra tag thử nghiệm @all và @Hồng Hoàng xem có hiển thị tag xanh không nhé!",
		},
	}
	c.WriteJSON(sendReq)
	var sendResp Frame
	c.ReadJSON(&sendResp)
	fmt.Printf("Send: %+v\n", sendResp)

	time.Sleep(3 * time.Second)
}
