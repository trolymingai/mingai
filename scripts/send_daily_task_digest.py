#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
send_daily_task_digest.py
Gửi báo cáo tổng hợp task vụ cuối ngày đến từng nhân sự phụ trách:
1. Quét Odoo ERP các task chưa hoàn tất (stage_id != 6).
2. Gom task theo từng nhân sự dựa vào mapping hr.employee (work_phone -> Zalo UID).
3. Gửi tin nhắn Zalo riêng (Direct Message) kèm link đăng nhập trực tiếp vào từng task.
4. Cung cấp hướng dẫn báo xong 2 chiều qua Trợ lý Ming.
"""

import sys
import os
import json
import subprocess
import xmlrpc.client
import datetime

ODOO_URL = "http://172.18.0.1:18070"
ODOO_DB = "odoo_minghouse"
ODOO_UID = 2
ODOO_KEY = "1362a613017363da65d6cbb7b3c831fa68a7a71e"
BASE_ERP_URL = "https://erp.mingcoffeemore.com"

def get_odoo_models():
    return xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)

def send_zalo_direct(to_uid, message):
    js_code = f"""
const ws = new WebSocket('ws://127.0.0.1:18790/ws');
ws.addEventListener('open', () => {{
    ws.send(JSON.stringify({{
        type: 'req',
        id: '1',
        method: 'connect',
        params: {{
            token: 'eae9134b7b6014847a75303456605872',
            user_id: '3322195382887364919'
        }}
    }}));
}});
ws.addEventListener('message', (event) => {{
    const data = JSON.parse(event.data);
    if (data.id === '1' && data.ok) {{
        ws.send(JSON.stringify({{
            type: 'req',
            id: '2',
            method: 'send',
            params: {{
                channel: 'zalo-ming-ai',
                to: '{to_uid}',
                message: {json.dumps(message, ensure_ascii=False)}
            }}
        }}));
        setTimeout(() => process.exit(0), 2000);
    }}
}});
"""
    tmp_path = f"/tmp/send_digest_{to_uid}.js"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(js_code)
    try:
        res = subprocess.run(['node', tmp_path], capture_output=True, text=True, timeout=10)
        return res.returncode == 0
    except Exception as e:
        print(f"Lỗi gửi tin Zalo tới {to_uid}: {e}")
        return False

def build_task_digest():
    models = get_odoo_models()
    now_vn = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))

    # 1. Get employees mapping
    emps = models.execute_kw(ODOO_DB, ODOO_UID, ODOO_KEY, 'hr.employee', 'search_read', [
        [('work_phone', '!=', False), ('user_id', '!=', False)]
    ], {'fields': ['id', 'name', 'user_id', 'work_phone']})

    user_to_emp = {}
    for e in emps:
        uid = e['user_id'][0]
        user_to_emp[uid] = {
            'name': e['name'],
            'zalo_id': e['work_phone'],
            'emp_id': e['id']
        }

    # 2. Get active tasks (stage_id != 6, excluding repetitive checklist surveys)
    tasks = models.execute_kw(ODOO_DB, ODOO_UID, ODOO_KEY, 'project.task', 'search_read', [
        [('stage_id', '!=', 6), ('name', 'not ilike', 'Checklist')]
    ], {'fields': ['id', 'name', 'project_id', 'user_ids', 'stage_id', 'date_deadline', 'create_uid'], 'order': 'id desc'})

    # 3. Group by employee
    emp_tasks = {}
    for t in tasks:
        for u in t.get('user_ids', []):
            if u in user_to_emp:
                emp_info = user_to_emp[u]
                zid = emp_info['zalo_id']
                if zid not in emp_tasks:
                    emp_tasks[zid] = {'info': emp_info, 'tasks': []}
                emp_tasks[zid]['tasks'].append(t)

    return emp_tasks, now_vn

def format_message(emp_name, tasks, now_vn):
    date_str = now_vn.strftime('%d/%m/%Y')
    msg = f"📋 [MING AI - TỔNG HỢP NHIỆM VỤ CUỐI NGÀY {date_str}]\n"
    msg += f"Chào bạn {emp_name}! Hiện tại bạn đang phụ trách {len(tasks)} đầu việc trên hệ thống Odoo ERP:\n\n"

    for idx, t in enumerate(tasks, 1):
        tid = t['id']
        tname = t['name']
        deadline = t.get('date_deadline') or "Đang xử lý"
        link = f"{BASE_ERP_URL}/web#id={tid}&model=project.task&view_type=form"
        msg += f"{idx}️⃣ Task #{tid}: {tname}\n"
        msg += f"   • Hạn chót: {deadline}\n"
        msg += f"   • Link vào task: {link}\n\n"

    msg += "💡 CÁCH HOÀN TẤT ĐẦU VIỆC:\n"
    msg += "• Cách 1: Bấm vào link tương ứng ở trên để đăng nhập Odoo và bấm nút [Hoàn tất].\n"
    msg += "• Cách 2: Bạn chỉ cần nhắn lại cho Trợ lý Ming: 'Đã xong Task [Mã số]' (kèm ảnh nghiệm thu nếu có). Ming sẽ tự động kiểm tra xác nhận với người giao việc và bấm Hoàn tất giúp bạn nghen!\n\n"
    msg += "✨ Chú tâm từng chi tiết, trọn vẹn từng tách cà phê."
    return msg

def main():
    dry_run = '--dry-run' in sys.argv
    target_uid = None
    for arg in sys.argv:
        if arg.startswith('--target='):
            target_uid = arg.split('=')[1]

    emp_tasks, now_vn = build_task_digest()
    print(f"[{now_vn}] Tìm thấy {len(emp_tasks)} nhân sự có task đang xử lý.")

    for zid, data in emp_tasks.items():
        if target_uid and zid != target_uid:
            continue
        emp_name = data['info']['name']
        tasks = data['tasks']
        msg = format_message(emp_name, tasks, now_vn)

        print(f"\n==================== [TO: {emp_name} - Zalo: {zid}] ====================")
        print(msg)

        if not dry_run:
            ok = send_zalo_direct(zid, msg)
            status_str = "THÀNH CÔNG" if ok else "THẤT BẠI"
            print(f"-> Gửi tin nhắn {status_str} tới {emp_name} ({zid})")

if __name__ == '__main__':
    main()
