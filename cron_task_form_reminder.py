#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cron_task_form_reminder.py
Hệ thống điều phối nhắc việc biểu mẫu tự động cho Ming Coffee AI.
Tính năng:
1. Tự động quét (Auto-Detector) tin nhắn Zalo (chat riêng & chat nhóm) để phát hiện nhân sự báo xong/đừng nhắc.
2. Tự động gạch tên (Auto-Exclude) khỏi danh sách nhắc việc định kỳ.
3. Hỗ trợ cờ --scan-only để chạy định kỳ quét nền liên tục.
4. Gửi nhắc việc định kỳ (09h00, 14h00, 13h00 chặng cuối) cho những ai CÒN PENDING.
"""

import datetime
import json
import subprocess
import os
import sys
import re

TRACKING_FILE = '/opt/goclaw/task_form_tracking.json'
if not os.path.exists(TRACKING_FILE):
    TRACKING_FILE = '/var/lib/docker/volumes/goclaw_goclaw-workspace/_data/task_form_tracking.json'

def scan_and_auto_exclude():
    """Quét PostgreSQL để phát hiện nhân sự đã chat xong hoặc xin đừng nhắc."""
    if not os.path.exists(TRACKING_FILE):
        return []
    
    with open(TRACKING_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    pending_uids = {uid: info['name'] for uid, info in data.items() if info.get('status') == 'pending'}
    if not pending_uids:
        return []

    cmd = [
        "docker", "exec", "-i", "goclaw-postgres-1", "psql", "-U", "goclaw", "-d", "goclaw",
        "-t", "-A", "-c",
        "SELECT session_key, user_id, messages FROM sessions WHERE updated_at > NOW() - INTERVAL '3 days';"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return list(pending_uids.values())

    keywords = [
        r'xong\s*rồi', r'đã\s*xong', r'làm\s*rồi', r'làm\s*xong', r'nộp\s*rồi', 
        r'đã\s*nộp', r'đã\s*điền', r'điền\s*rồi', r'gửi\s*rồi', r'đã\s*gửi', 
        r'hoàn\s*thành', r'đừng\s*nhắc', r'không\s*cần\s*nhắc', r'hủy\s*lịch\s*nhắc',
        r'\bdone\b'
    ]
    pattern = re.compile('|'.join(keywords), re.IGNORECASE)

    updated = False
    lines = res.stdout.strip().split('\n')
    for line in lines:
        if not line or '|' not in line:
            continue
        parts = line.split('|', 2)
        if len(parts) < 3:
            continue
        sk, session_user_id, msgs_raw = parts
        try:
            msgs = json.loads(msgs_raw)
        except Exception:
            continue

        is_direct = ":direct:" in sk
        direct_uid = sk.split(":direct:")[-1] if is_direct else None

        for m in msgs[-10:]:
            role = m.get('role', '')
            content = m.get('content', '')
            if role != 'user':
                continue

            body = re.sub(r'^\[.*?\]\s*', '', content).strip()
            if not pattern.search(body):
                continue

            matched_uid = None
            if is_direct and direct_uid in pending_uids:
                matched_uid = direct_uid
            else:
                m_sender = re.search(r'(?:Người gửi|From):\s*([^\n\]]+)', content)
                if m_sender:
                    sender_name = m_sender.group(1).strip()
                    for uid, name in pending_uids.items():
                        n_clean = name.lower().replace("anh ", "").replace("chị ", "").strip()
                        s_clean = sender_name.lower().replace("anh ", "").replace("chị ", "").strip()
                        if n_clean == s_clean or n_clean in s_clean or s_clean in n_clean:
                            matched_uid = uid
                            break

            if matched_uid and matched_uid in data and data[matched_uid].get('status') == 'pending':
                emp_name = data[matched_uid]['name']
                now_str = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).strftime("%Y-%m-%d %H:%M:%S")
                clean_body = body.replace('\n', ' ')[:80]
                data[matched_uid]['status'] = 'completed'
                data[matched_uid]['completed_at'] = now_str
                data[matched_uid]['note'] = f"Tự động gạch tên do chat: '{clean_body}'"
                print(f"[{now_str}] [AUTO-EXCLUDE] Gạch tên {emp_name} (UID: {matched_uid}) vì chat: '{clean_body}'")
                updated = True
                del pending_uids[matched_uid]

    if updated:
        with open(TRACKING_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return list(pending_uids.values())

def main():
    NOW_VN = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    DEADLINE = datetime.datetime(2026, 11, 22, 17, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=7)))

    # Quét cập nhật tự động trước
    remaining_pending = scan_and_auto_exclude()

    # Nếu chạy ở chế độ chỉ quét nền (--scan-only)
    if '--scan-only' in sys.argv:
        print(f"[{NOW_VN}] Quét nền hoàn tất. Còn lại {len(remaining_pending)} người pending: {remaining_pending}")
        sys.exit(0)

    # Kiểm tra hạn chót
    if NOW_VN > DEADLINE:
        print(f"[{NOW_VN}] Đã qua deadline (17h00 ngày 22/11/2026). Dừng gửi nhắc việc.")
        sys.exit(0)

    remaining = DEADLINE - NOW_VN
    hours_left = remaining.total_seconds() / 3600.0
    if hours_left <= 0:
        sys.exit(0)

    is_final_4h = (hours_left <= 4.5 and hours_left >= 3.0)

    # Đọc lại danh sách pending từ file
    recipients = []
    if os.path.exists(TRACKING_FILE):
        with open(TRACKING_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for uid, info in data.items():
                if info.get('status') == 'pending':
                    recipients.append({"uid": uid, "name": info.get('name', 'Bạn')})

    if not recipients:
        print(f"[{NOW_VN}] Tất cả nhân sự đã hoàn tất form. Không có ai cần nhắc!")
        sys.exit(0)

    print(f"[{NOW_VN}] Danh sách nhân sự còn cần nhắc ({len(recipients)} người): {[r['name'] for r in recipients]}")

    if '--dry-run' in sys.argv:
        print(f"[{NOW_VN}] [DRY-RUN] Sẽ gửi tin nhắn nhắc nhở tới {len(recipients)} người trên.")
        sys.exit(0)

    js_code = """
const ws = new WebSocket('ws://127.0.0.1:18790/ws');
const recipients = %s;
const isFinal = %s;
let reqId = 200;

function sendMsg(to, text) {
    reqId++;
    ws.send(JSON.stringify({
        type: 'req',
        id: String(reqId),
        method: 'send',
        params: {
            channel: 'zalo-ming-ai',
            to: to,
            message: text
        }
    }));
}

ws.addEventListener('open', () => {
    ws.send(JSON.stringify({
        type: 'req',
        id: '1',
        method: 'connect',
        params: {
            token: 'eae9134b7b6014847a75303456605872',
            user_id: '3322195382887364919'
        }
    }));
});

ws.addEventListener('message', (event) => {
    const data = JSON.parse(event.data);
    if (data.id === '1' && data.ok) {
        for (const r of recipients) {
            let msg = '';
            if (isFinal) {
                msg = `⚠️ [MING AI - NHẮC HẸN KHẨN CẤP CHẶNG CUỐI]\n\nChào bạn ${r.name}!\nChỉ còn chưa đầy 4 TIẾNG nữa là đến hạn chót (17h00 hôm nay 22/11/2026) theo chỉ đạo của Anh Minh CEO.\n\nBạn vui lòng hoàn tất ngay biểu mẫu liệt kê đầu việc trong ca để hệ thống tổng hợp báo cáo cho Ban Giám Đốc nhé:\n👉 Link điền form: https://forms.gle/ZRkLuVJNd6K8U6BU7\n\n✨ Chú tâm từng chi tiết, trọn vẹn từng tách cà phê.`;
            } else {
                msg = `☕ [MING AI] Nhắc việc định kỳ biểu mẫu công việc ca\n\nChào bạn ${r.name}!\nMing AI gửi lời nhắc định kỳ theo chỉ đạo của Anh Minh CEO về việc hoàn tất biểu mẫu ghi nhận đầu việc ca:\n\n👉 Link điền form: https://forms.gle/ZRkLuVJNd6K8U6BU7\n⏰ Hạn chót nộp: Trước 17h00 ngày 22/11/2026.\n\nNếu bạn đã hoàn tất điền form rồi thì bạn có thể nhắn lại để Ming ghi nhận gạch tên nhé! Chúc bạn một ca làm việc tràn đầy năng lượng!\n\n✨ Chú tâm từng chi tiết, trọn vẹn từng tách cà phê.`;
            }
            sendMsg(r.uid, msg);
        }
        setTimeout(() => process.exit(0), 3000);
    }
});
""" % (json.dumps(recipients), "true" if is_final_4h else "false")

    with open('/tmp/cron_run.js', 'w', encoding='utf-8') as f:
        f.write(js_code)

    subprocess.run(['node', '/tmp/cron_run.js'], capture_output=True, text=True)
    print(f"[{NOW_VN}] Đã gửi thông báo nhắc việc thành công tới {len(recipients)} nhân sự còn pending.")

if __name__ == '__main__':
    main()
