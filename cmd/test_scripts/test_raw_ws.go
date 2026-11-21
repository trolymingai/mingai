package main

import (
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/gorilla/websocket"
)

func main() {
	header := http.Header{}
	c, _, err := websocket.DefaultDialer.Dial("ws://127.0.0.1:18790/ws", header)
	if err != nil {
		log.Fatalf("dial: %v", err)
	}
	defer c.Close()

	// 1. Connect
	connectReq := `{"type":"req","id":"c1","method":"connect","params":{"token":"eae9134b7b6014847a75303456605872","user_id":"system"}}`
	c.WriteMessage(websocket.TextMessage, []byte(connectReq))
	_, msg, _ := c.ReadMessage()
	fmt.Printf("Raw Connect Resp: %s\n", string(msg))

	// Send message WITH @all and @Hồng Hoàng
	text := "Thử nghiệm tag thông báo: @all và @Hồng Hoàng vui lòng kiểm tra xem thẻ tag xanh có nổi bật không nhé!"
	sendReq := fmt.Sprintf(`{"type":"req","id":"s1","method":"send","params":{"channel":"zalo-ming-ai","to":"552328793123364999","message":%q}}`, text)
	c.WriteMessage(websocket.TextMessage, []byte(sendReq))
	_, msg, _ = c.ReadMessage()
	fmt.Printf("Raw Send Resp: %s\n", string(msg))

	time.Sleep(2 * time.Second)
}
