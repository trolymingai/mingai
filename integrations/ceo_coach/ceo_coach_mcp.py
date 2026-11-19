#!/usr/bin/env python3
import json
import os
import sys
import time
import datetime
import psycopg2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
AUDIT_LOG = os.path.join(BASE_DIR, "audit.log")
os.makedirs(BACKUP_DIR, exist_ok=True)

DSN = os.environ.get("GOCLAW_POSTGRES_DSN", "postgres://goclaw:cd7bc3ebe5d9b7aeda4af251ecdac47e@postgres:5432/goclaw?sslmode=disable")
AUTHORIZED_CEO_UID = "3322195382887364919"
AUTHORIZED_NAMES = ["Vương Minh", "Dương Vương Minh", "Anh Minh", "CEO"]
AGENT_KEY = "ming-ai"
AGENT_ID = "01a1e29b-fcc0-74c1-acee-6321513a68ed"
TENANT_ID = "0193a5b0-7000-7000-8000-000000000001"

def is_authorized(uid, name):
    uid_str = str(uid).strip() if uid else ""
    name_str = str(name).strip() if name else ""
    if uid_str == AUTHORIZED_CEO_UID:
        return True
    if any(n.lower() in name_str.lower() for n in AUTHORIZED_NAMES):
        return True
    return False

def log_audit(action, details):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] ACTION: {action} | DETAILS: {json.dumps(details, ensure_ascii=False)}\n"
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(entry)

def tool_view_prompt(args):
    target = args.get("target", "summary")
    try:
        conn = psycopg2.connect(DSN)
        cur = conn.cursor()
        cur.execute("SELECT frontmatter FROM agents WHERE agent_key = %s;", (AGENT_KEY,))
        row = cur.fetchone()
        frontmatter = row[0] if row and row[0] else ""
        
        cur.execute("SELECT file_name, content FROM agent_context_files WHERE agent_id = %s ORDER BY file_name;", (AGENT_ID,))
        files = cur.fetchall()
        conn.close()

        if target == "summary":
            return {
                "ok": True,
                "agent": AGENT_KEY,
                "frontmatter_length": len(frontmatter),
                "context_files": [f[0] for f in files],
                "message": "Để xem chi tiết, chọn target='frontmatter' hoặc target='ceo_directives'."
            }
        elif target == "frontmatter":
            return {
                "ok": True,
                "frontmatter": frontmatter
            }
        elif target == "ceo_directives":
            ceo_f = [f[1] for f in files if f[0] == "CEO_DIRECTIVES.md"]
            return {
                "ok": True,
                "ceo_directives": ceo_f[0] if ceo_f else "Chưa có file CEO_DIRECTIVES.md riêng biệt."
            }
        else:
            return {
                "ok": True,
                "frontmatter": frontmatter,
                "context_files": {f[0]: f[1] for f in files}
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}

def tool_update_prompt(args):
    uid = args.get("requester_zalo_uid")
    name = args.get("requester_name")
    operation = args.get("operation", "append_rule")
    title = args.get("rule_title", "Quy tắc mới từ Anh Minh CEO")
    content = args.get("instruction_content", "")
    reason = args.get("reason", "Huấn luyện 1-1 qua Zalo cá nhân")

    if not is_authorized(uid, name):
        return {
            "ok": False,
            "error": f"LỖI PHÂN QUYỀN (ACCESS DENIED): Chỉ duy nhất Anh Minh CEO (Zalo UID: {AUTHORIZED_CEO_UID}) mới có thẩm quyền huấn luyện, sửa đổi Prompt và khóa cứng quy tắc làm việc của Ming AI.",
            "authorized": False
        }

    if not content.strip():
        return {"ok": False, "error": "Nội dung chỉ đạo (instruction_content) không được để trống."}

    try:
        conn = psycopg2.connect(DSN)
        cur = conn.cursor()
        cur.execute("SELECT frontmatter FROM agents WHERE agent_key = %s;", (AGENT_KEY,))
        row = cur.fetchone()
        current_frontmatter = row[0] if row and row[0] else ""

        # Make backup file
        ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"frontmatter_{ts_str}.md")
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(current_frontmatter)

        # Prepare new directive block
        formatted_rule = f"""
### [QUY TẮC KHÓA CỨNG TỪ CEO DƯƠNG VƯƠNG MINH - NGÀY {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}]
**Tiêu đề**: {title}
**Lý do**: {reason}
**Nội dung quy tắc / phong cách làm việc**:
{content.strip()}
"""

        header = "## QUY TẮC BẤT KHẢ XÂM PHẠM TỪ CEO DƯƠNG VƯƠNG MINH (HUẤN LUYỆN 1-1)"
        if header in current_frontmatter:
            new_frontmatter = current_frontmatter + "\n" + formatted_rule
        else:
            new_frontmatter = current_frontmatter + f"\n\n{header}\nCác quy tắc dưới đây do đích thân CEO Dương Vương Minh huấn luyện trực tiếp 1-1 và có hiệu lực thi hành cao nhất trên toàn bộ hệ thống Ming AI:\n" + formatted_rule

        # Update agents.frontmatter
        cur.execute("UPDATE agents SET frontmatter = %s, updated_at = NOW() WHERE agent_key = %s;", (new_frontmatter, AGENT_KEY))

        # Also update or insert into agent_context_files as CEO_DIRECTIVES.md
        cur.execute("SELECT content FROM agent_context_files WHERE agent_id = %s AND file_name = 'CEO_DIRECTIVES.md';", (AGENT_ID,))
        cf_row = cur.fetchone()
        if cf_row:
            existing_cf = cf_row[0] or ""
            new_cf = existing_cf + "\n" + formatted_rule
            cur.execute("UPDATE agent_context_files SET content = %s, updated_at = NOW() WHERE agent_id = %s AND file_name = 'CEO_DIRECTIVES.md';", (new_cf, AGENT_ID))
        else:
            new_cf = f"# CEO DIRECTIVES - QUY TẮC VẬN HÀNH KHÓA CỨNG TỪ CEO\n{formatted_rule}"
            cur.execute("""
                INSERT INTO agent_context_files (id, agent_id, file_name, content, created_at, updated_at, tenant_id)
                VALUES (gen_random_uuid(), %s, 'CEO_DIRECTIVES.md', %s, NOW(), NOW(), %s);
            """, (AGENT_ID, new_cf, TENANT_ID))

        conn.commit()
        conn.close()

        log_audit("UPDATE_PROMPT", {
            "uid": uid,
            "name": name,
            "title": title,
            "operation": operation,
            "backup": backup_path,
            "content_preview": content[:100]
        })

        return {
            "ok": True,
            "status": "LOCKED_IN_PRODUCTION",
            "message": f"Đã khóa cứng thành công quy tắc '{title}' vào nhân hệ thống của Ming AI theo chỉ đạo của Anh Minh CEO!",
            "backup_version": f"frontmatter_{ts_str}.md",
            "enforced_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        return {"ok": False, "error": f"Lỗi khi cập nhật cơ sở dữ liệu: {str(e)}"}

def tool_rollback(args):
    uid = args.get("requester_zalo_uid")
    name = args.get("requester_name")
    version = args.get("backup_version", "latest")

    if not is_authorized(uid, name):
        return {
            "ok": False,
            "error": "LỖI PHÂN QUYỀN: Chỉ duy nhất Anh Minh CEO mới có quyền rollback prompt."
        }

    try:
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("frontmatter_")])
        if not backups:
            return {"ok": False, "error": "Chưa có bản backup nào."}

        target_file = backups[-1] if version == "latest" else version
        target_path = os.path.join(BACKUP_DIR, target_file)
        if not os.path.exists(target_path):
            return {"ok": False, "error": f"Không tìm thấy file backup: {target_file}"}

        with open(target_path, "r", encoding="utf-8") as f:
            restored_content = f.read()

        conn = psycopg2.connect(DSN)
        cur = conn.cursor()
        cur.execute("UPDATE agents SET frontmatter = %s, updated_at = NOW() WHERE agent_key = %s;", (restored_content, AGENT_KEY))
        conn.commit()
        conn.close()

        log_audit("ROLLBACK", {"uid": uid, "name": name, "restored_from": target_file})
        return {
            "ok": True,
            "message": f"Đã khôi phục thành công prompt về phiên bản {target_file}!"
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

TOOLS = {
    "ceo_view_system_prompt_and_rules": {
        "description": "Xem toàn bộ nội dung Prompt hệ thống, các quy tắc vận hành và chỉ thị huấn luyện của Ming AI (dành cho Anh Minh CEO).",
        "schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "enum": ["summary", "frontmatter", "ceo_directives", "all"], "default": "summary"}
            }
        },
        "fn": tool_view_prompt
    },
    "ceo_update_prompt_and_behavior": {
        "description": "Sửa đổi, cập nhật hoặc khóa cứng Prompt, quy tắc vận hành, văn phong và cách nhắn tin làm việc của Ming AI trực tiếp qua chat cá nhân 1-1. CHỈ DUY NHẤT ANH MINH CEO (Zalo UID: 3322195382887364919) MỚI ĐƯỢC PHÉP THỰC HIỆN.",
        "schema": {
            "type": "object",
            "properties": {
                "requester_zalo_uid": {"type": "string", "description": "UID Zalo của người gửi yêu cầu (bắt buộc)"},
                "requester_name": {"type": "string", "description": "Tên người gửi yêu cầu (ví dụ: 'Vương Minh', 'Anh Minh')"},
                "operation": {"type": "string", "enum": ["append_rule", "update_tone_and_style", "patch_prompt", "set_hard_rule"], "description": "Hành động cập nhật"},
                "rule_title": {"type": "string", "description": "Tiêu đề ngắn gọn của quy tắc hoặc phong cách cần khóa cứng"},
                "instruction_content": {"type": "string", "description": "Nội dung chỉ đạo, quy tắc hoặc prompt chi tiết mà Anh Minh yêu cầu Ming AI thực hiện"},
                "reason": {"type": "string", "description": "Lý do hoặc ghi chú của buổi huấn luyện 1-1"}
            },
            "required": ["requester_zalo_uid", "rule_title", "instruction_content"]
        },
        "fn": tool_update_prompt
    },
    "ceo_rollback_prompt": {
        "description": "Khôi phục lại phiên bản prompt trước đó nếu cần (chỉ dành riêng cho Anh Minh CEO).",
        "schema": {
            "type": "object",
            "properties": {
                "requester_zalo_uid": {"type": "string", "description": "UID Zalo của người gửi yêu cầu"},
                "backup_version": {"type": "string", "description": "Mã backup cần khôi phục (hoặc 'latest')"}
            },
            "required": ["requester_zalo_uid"]
        },
        "fn": tool_rollback
    }
}

def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()

def handle(req):
    method = req.get("method")
    rid = req.get("id")
    try:
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "ceo-coach", "version": "1.0.0"}}}
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": rid, "result": {"tools": [
                {"name": name, "description": meta["description"], "inputSchema": meta["schema"]}
                for name, meta in TOOLS.items()
            ]}}
        if method == "tools/call":
            params = req.get("params") or {}
            name = params.get("name")
            args = params.get("arguments") or {}
            if name not in TOOLS:
                raise RuntimeError("Unknown tool: " + str(name))
            result = TOOLS[name]["fn"](args)
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}}
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}}
    except Exception as e:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": str(e)}}

def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        res = handle(req)
        if res is not None:
            send(res)

if __name__ == "__main__":
    main()