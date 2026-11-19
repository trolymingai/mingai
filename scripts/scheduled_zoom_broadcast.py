import os
import sys
import json
import time
import datetime
import websocket

FLAG_FILE = "/tmp/zoom_broadcast_sent.flag"
GATEWAY_WS = "ws://127.0.0.1:18790/ws"
TOKEN = "eae9134b7b6014847a75303456605872"
TARGET_EPOCH = 1795074600.0  # 2026-11-19 07:50:00 UTC = 14:50:00 VN

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

MESSAGE = """📢 [THÔNG BÁO VÀO ZOOM - 15:00 CHIỀU NAY]
Khởi động Chuyển Đổi Số AI Ming - Chuỗi Series Huấn Luyện AI

Kính mời toàn thể anh chị em tham gia buổi hướng dẫn sử dụng Trợ Lý Ming:
👉 Link Zoom: https://us06web.zoom.us/j/84085126014
🆔 Meeting ID: 840 8512 6014

(Chương trình bắt đầu lúc 15:00, mọi người vào trước 10 phút để ổn định nhé!)"""

def main():
    if os.path.exists(FLAG_FILE):
        print(f"[{datetime.datetime.now()}] Broadcast already completed. Exiting.")
        return

    now = time.time()
    diff = TARGET_EPOCH - now
    if diff > 0:
        print(f"[{datetime.datetime.now()}] Sleeping {diff:.1f}s until 14:50:00 VN (07:50:00 UTC)...")
        time.sleep(diff)

    print(f"[{datetime.datetime.now()}] TIME REACHED! Initiating broadcast to {len(GROUPS)} groups...")

    try:
        ws = websocket.create_connection(GATEWAY_WS, timeout=15)
        connect_req = {
            "type": "req",
            "id": "c1",
            "method": "connect",
            "params": {"token": TOKEN, "user_id": "system"}
        }
        ws.send(json.dumps(connect_req))
        conn_res = ws.recv()
        print(f"Gateway connected: {conn_res}")
    except Exception as e:
        print(f"Failed to connect to gateway WS: {e}")
        return

    sent_count = 0
    for idx, grp in enumerate(GROUPS):
        gid = grp["id"]
        gname = grp["name"]
        send_req = {
            "type": "req",
            "id": f"zoom_{gid}_{int(time.time()*1000)}",
            "method": "send",
            "params": {
                "channel": "zalo-ming-ai",
                "to": str(gid),
                "message": MESSAGE
            }
        }
        try:
            ws.send(json.dumps(send_req))
            res = ws.recv()
            print(f"[{idx+1}/{len(GROUPS)}] Sent to '{gname}' ({gid}): {res}")
            sent_count += 1
        except Exception as ex:
            print(f"[{idx+1}/{len(GROUPS)}] ERROR sending to '{gname}' ({gid}): {ex}")
        time.sleep(1.2)

    try:
        ws.close()
    except Exception:
        pass

    with open(FLAG_FILE, "w", encoding="utf-8") as f:
        f.write(f"Completed at {datetime.datetime.now()} - {sent_count}/{len(GROUPS)} groups")

    print(f"[{datetime.datetime.now()}] BROADCAST FINISHED! Sent {sent_count}/{len(GROUPS)} groups.")

if __name__ == "__main__":
    main()
