import os
import sys
import json
import time
import datetime
import sqlite3
import xmlrpc.client
import subprocess

ODOO_URL = os.environ.get("ODOO_URL", "http://172.18.0.1:18070")
ODOO_DB = os.environ.get("ODOO_DB", "odoo_minghouse")
ODOO_UID = int(os.environ.get("ODOO_UID", "2"))
ODOO_API_KEY = os.environ.get("ODOO_API_KEY", "1362a613017363da65d6cbb7b3c831fa68a7a71e")

BRANCH_GROUPS = {
    "PHUOC_THE": "8145378988362298919",
    "A2": "5944076628365845072",
    "LE_DUAN": "2170546658158087218",
    "A3": "5435289813534943299",
    "PHAN_RI": "6099730162709364619",
    "TEST": "552328793123364999",
    "GENERAL": "552328793123364999"
}

PROJECT_TO_GROUP = [
    (["PHƯỚC THỂ", "PHUOC THE", "PT"], BRANCH_GROUPS["PHUOC_THE"]),
    (["A2", "GOO-A2"], BRANCH_GROUPS["A2"]),
    (["LÊ DUẨN", "LE DUAN", "LD"], BRANCH_GROUPS["LE_DUAN"]),
    (["A3", "LIÊN HƯƠNG", "LIEN HUONG"], BRANCH_GROUPS["A3"]),
    (["PHAN RÍ", "PHAN RI", "PR"], BRANCH_GROUPS["PHAN_RI"]),
    (["TEST"], BRANCH_GROUPS["TEST"]),
]

DB_PATH = "/opt/goclaw/task_reminders.sqlite"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS task_reminders (
        task_id INTEGER PRIMARY KEY,
        name TEXT,
        deadline TEXT,
        t10_sent INTEGER DEFAULT 0,
        t0_sent INTEGER DEFAULT 0,
        completed INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT
    );
    """)
    conn.commit()
    conn.close()

def get_odoo_models():
    return xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)

def resolve_group(project_name):
    if not project_name:
        return BRANCH_GROUPS["GENERAL"]
    p_upper = project_name.upper()
    for keywords, gid in PROJECT_TO_GROUP:
        for kw in keywords:
            if kw in p_upper:
                return gid
    return BRANCH_GROUPS["GENERAL"]

def send_goclaw_notification(deliver_to, message):
    sql = f"""
    INSERT INTO cron_jobs (
        agent_id, name, enabled, schedule_kind, run_at, next_run_at, delete_after_run,
        deliver, deliver_channel, deliver_to, payload, tenant_id
    ) VALUES (
        '01a1e29b-fcc0-74c1-acee-6321513a68ed',
        'task_remind_{int(time.time()*1000)}',
        true,
        'at',
        now() + interval '1 second',
        now() + interval '1 second',
        true,
        true,
        'zalo-ming-ai',
        '{deliver_to}',
        $JSON${json.dumps({'kind': 'agent_turn', 'message': message}, ensure_ascii=False)}$JSON$,
        '0193a5b0-7000-7000-8000-000000000001'
    );
    """
    cmd = ["docker", "exec", "-i", "goclaw-postgres-1", "psql", "-U", "goclaw", "-d", "goclaw", "-c", sql]
    try:
        subprocess.run(cmd, capture_output=True, timeout=5, check=True)
        print(f"[{datetime.datetime.now()}] Notification queued to {deliver_to}")
    except Exception as e:
        print(f"[{datetime.datetime.now()}] Failed to queue notification: {e}")

def check_tasks():
    try:
        models = get_odoo_models()
        tasks = models.execute_kw(
            ODOO_DB, ODOO_UID, ODOO_API_KEY,
            "project.task", "search_read",
            [[["state", "in", ["01_in_progress", "02_changes_requested"]], ["date_deadline", "!=", False]]],
            {"fields": ["id", "name", "project_id", "date_deadline", "user_ids", "description"]}
        )
    except Exception as e:
        print(f"Error connecting to Odoo: {e}")
        return

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_vn = now_utc + datetime.timedelta(hours=7)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    for t in tasks:
        tid = t["id"]
        tname = t["name"]
        pname = t["project_id"][1] if t.get("project_id") else "Toàn Hệ Thống"
        d_str = t["date_deadline"] # e.g. "2026-11-19" or "2026-11-19 14:00:00"

        # Parse deadline
        try:
            if len(d_str) == 10:
                # date only -> default 22:00 VN
                dt_vn = datetime.datetime.strptime(f"{d_str} 22:00:00", "%Y-%m-%d %H:%M:%S")
            else:
                dt_vn = datetime.datetime.strptime(d_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue

        diff_minutes = (dt_vn - now_vn.replace(tzinfo=None)).total_seconds() / 60.0

        # Check DB tracking
        c.execute("SELECT t10_sent, t0_sent FROM task_reminders WHERE task_id = ?", (tid,))
        row = c.fetchone()
        if not row:
            c.execute("INSERT INTO task_reminders (task_id, name, deadline, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                      (tid, tname, d_str, str(now_vn), str(now_vn)))
            conn.commit()
            t10_sent, t0_sent = 0, 0
        else:
            t10_sent, t0_sent = row[0], row[1]

        target_group = resolve_group(pname)
        time_str = dt_vn.strftime("%H:%M %d/%m")

        # T-10m reminder
        if 0 < diff_minutes <= 10.5 and not t10_sent:
            msg = f"⏰ [NHẮC VIỆC - CÒN 10 PHÚT]\n\n" \
                  f"📋 Nhiệm vụ #{tid}: {tname}\n" \
                  f"⏳ Hạn chót: {time_str} (Còn khoảng 10 phút)\n" \
                  f"📍 Chi nhánh: {pname}\n\n" \
                  f"👉 Nhân sự phụ trách vui lòng khẩn trương hoàn thành công việc, chụp ảnh bằng chứng (Proof of Work) và gửi vào nhóm tag Ming AI để CHT nghiệm thu nhé!"
            send_goclaw_notification(target_group, msg)
            c.execute("UPDATE task_reminders SET t10_sent = 1, updated_at = ? WHERE task_id = ?", (str(now_vn), tid))
            conn.commit()

        # T-0m deadline reached
        elif -30.0 <= diff_minutes <= 0.0 and not t0_sent:
            msg = f"🚨 [HẾT HẠN NHIỆM VỤ]\n\n" \
                  f"📋 Nhiệm vụ #{tid}: {tname} ĐÃ ĐẾN HẠN CHÓT ({time_str})!\n" \
                  f"📍 Chi nhánh: {pname}\n\n" \
                  f"👉 Nhân sự: Vui lòng báo cáo tiến độ và gửi ảnh thực tế ngay.\n" \
                  f"👉 Cửa hàng trưởng: Kính nhờ CHT kiểm tra và chỉ đạo tại chỗ."
            send_goclaw_notification(target_group, msg)
            c.execute("UPDATE task_reminders SET t0_sent = 1, updated_at = ? WHERE task_id = ?", (str(now_vn), tid))
            conn.commit()

    conn.close()

if __name__ == "__main__":
    init_db()
    check_tasks()
