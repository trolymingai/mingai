import json
import time
import datetime
import websocket

GATEWAY_WS = "ws://127.0.0.1:18790/ws"
TOKEN = "eae9134b7b6014847a75303456605872"

GROUPS = [
    {"id": "8145378988362298919", "name": "Goo Phước Thể | Tổng"},
    {"id": "5944076628365845072", "name": "Goo-A2|Tổng"},
    {"id": "2170546658158087218", "name": "Goo-Lê Duẩn| Tổng"},
    {"id": "7325150732309676165", "name": "MING A3|PC"},
    {"id": "5435289813534943299", "name": "MING A3|Tổng"},
    {"id": "8693932597578748554", "name": "MING-GOO|Pha chế"},
    {"id": "6214157677241296400", "name": "MING-Nơi chốn thứ 2"},
    {"id": "1865171399962457807", "name": "MING|Bán hàng"},
    {"id": "285073119289277145",  "name": "MING|CUNG ỨNG|CỬA HÀNG"},
    {"id": "3848125694699364170", "name": "MING|Quản lý"},
    {"id": "6099730162709364619", "name": "Ming PR|Tổng"},
    {"id": "2785144727994011019", "name": "Ming|Báo sự cố"},
    {"id": "552328793123364999",  "name": "Test Ming AI"},
]

MESSAGE = """Cảm ơn cả nhà đã tham gia buổi Zoom Khởi động Chuyển Đổi Số AI Ming chiều nay! 🙏

Mọi người có thể xem lại và ôn tập nội dung tại các link dưới đây:
📘 Tài liệu huấn luyện Buổi 1:
https://drive.google.com/file/d/1extzt_e66uDbDAQQaHV6a0UkpVv0CYAy/view?usp=sharing

🎧 File mp3 bỏ túi để nghe lại:
https://drive.google.com/file/d/1ged-nJgEVhwm1X7nJbY_xbT3j4T5ke4s/view?usp=sharing

📝 Script chi tiết:
https://docs.google.com/document/d/1alaqXOFTafl_1UgU2aRbW4kLI9sjudz2/edit?usp=sharing&ouid=101952506280857191480&rtpof=true&sd=true

📌 Bản tóm tắt:
https://docs.google.com/document/d/1I09nuRiLMv-tbVrqLOwIpOlK0Izxh8J8/edit?usp=sharing&ouid=101952506280857191480&rtpof=true&sd=true

Chúc cả nhà ứng dụng Trợ Lý Ming thật hiệu quả trong công việc hằng ngày! ✨"""

def send_all():
    ws = websocket.create_connection(GATEWAY_WS, timeout=15)
    connect_req = {
        "type": "req",
        "id": "c1",
        "method": "connect",
        "params": {"token": TOKEN}
    }
    ws.send(json.dumps(connect_req))
    resp = json.loads(ws.recv())
    print("Gateway connected:", resp.get("ok"))

    success_count = 0
    for idx, grp in enumerate(GROUPS, 1):
        req_id = f"recap_{grp['id']}_{int(time.time()*1000)}"
        msg_req = {
            "type": "req",
            "id": req_id,
            "method": "send",
            "params": {
                "channel": "zalo-ming-ai",
                "to": grp["id"],
                "message": MESSAGE
            }
        }
        ws.send(json.dumps(msg_req))
        res = json.loads(ws.recv())
        print(f"[{idx}/{len(GROUPS)}] Sent to '{grp['name']}' ({grp['id']}): ok={res.get('ok')}")
        if res.get("ok"):
            success_count += 1
        time.sleep(1.0)

    ws.close()
    print(f"[{datetime.datetime.now()}] DONE: Successfully sent to {success_count}/{len(GROUPS)} groups.")

if __name__ == '__main__':
    send_all()