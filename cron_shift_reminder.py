#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cron Shift Reminder (Cơ chế 2) - Ming Coffee AI
Quét tự động nhân sự đầu ca và gửi tin nhắn 1-1 nhắc nhở check-in / phát Thẻ kiểm tra công việc.
Đảm bảo chống spam: Chỉ gửi tối đa 1 lần/ca cho mỗi nhân sự.
"""

import sys
import os
import json
import datetime
import time
import websocket

sys.path.insert(0, '/opt/goclaw/skills/odoo-erp-operations/1')
import odoo_cli

STATE_FILE = '/tmp/shift_reminder_state.json'
GATEWAY_WS = 'ws://127.0.0.1:18790/ws'
TOKEN = 'eae9134b7b6014847a75303456605872'

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(state):
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Error saving state:", e)

def send_zalo_dm(chat_id, message):
    try:
        ws = websocket.create_connection(GATEWAY_WS, timeout=10)
        # Connect
        connect_req = {
            "type": "req",
            "id": "c1",
            "method": "connect",
            "params": {"token": TOKEN, "user_id": "system"}
        }
        ws.send(json.dumps(connect_req))
        ws.recv()
        
        # Send
        send_req = {
            "type": "req",
            "id": f"remind_{chat_id}_{int(time.time())}",
            "method": "send",
            "params": {
                "channel": "zalo-ming-ai",
                "to": str(chat_id),
                "message": message
            }
        }
        ws.send(json.dumps(send_req))
        res = ws.recv()
        ws.close()
        print(f"Sent DM to {chat_id}: {res}")
        return True
    except Exception as e:
        print(f"Failed to send DM to {chat_id}: {e}")
        return False

def run_roster_check():
    now_vn = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)
    today_str = now_vn.strftime("%Y-%m-%d")
    hour = now_vn.hour
    
    if hour < 12:
        shift_key = f"{today_str}_sang"
        shift_name = "Ca Sáng"
    elif hour < 17:
        shift_key = f"{today_str}_chieu"
        shift_name = "Ca Chiều"
    else:
        shift_key = f"{today_str}_toi"
        shift_name = "Ca Tối"
        
    print(f"=== RUNNING SHIFT ROSTER CHECK: {now_vn.strftime('%d/%m/%Y %H:%M:%S')} - {shift_name} ===")
    
    state = load_state()
    reminded_today = state.get(shift_key, [])
    
    models = odoo_cli.get_models()
    emps = models.execute_kw(
        odoo_cli.ODOO_DB, odoo_cli.ODOO_UID, odoo_cli.ODOO_API_KEY,
        "hr.employee", "search_read",
        [[("active", "=", True)]],
        {"fields": ["id", "name", "job_title", "work_phone", "mobile_phone", "department_id", "attendance_state"]}
    )
    
    print(f"Total active employees: {len(emps)}")
    
    for emp in emps:
        emp_id = emp["id"]
        emp_name = emp["name"]
        att_state = emp.get("attendance_state") or "checked_out"
        zalo_id = emp.get("work_phone") or emp.get("mobile_phone")
        
        # Nếu chưa điểm danh và có Zalo ID và chưa được nhắc trong ca này
        if att_state != "checked_in" and zalo_id and str(emp_id) not in reminded_today:
            msg = (
                f"☕ [MING AI] Chào bạn {emp_name}!
"
                f"Ca làm việc {shift_name} hôm nay đã bắt đầu. Khi bạn đến quán nhận ca, hãy nhắn 'vào ca' hoặc 'check-in' để Ming kích hoạt Thẻ kiểm tra công việc và điểm danh nhé!

"
                f"✨ Chúc bạn có một ca làm việc tràn đầy năng lượng và chú tâm!"
            )
            
            print(f"Sending proactive reminder to {emp_name} (Zalo: {zalo_id})...")
            send_zalo_dm(zalo_id, msg)
            reminded_today.append(str(emp_id))
            time.sleep(1)
            
    state[shift_key] = reminded_today
    save_state(state)
    print("Shift roster check completed successfully.")

if __name__ == "__main__":
    run_roster_check()
