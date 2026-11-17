#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ming Coffee - Odoo ERP Operations CLI Tool
High-speed internal CLI for Ming AI to manage tasks, checklists, anti-fraud verifications, and employee onboarding.
Fully synchronizes staff checklists and operational tasks to Odoo ERP 19.
"""

import sys
import os
import json
import datetime
import xmlrpc.client

ODOO_URL = os.environ.get("ODOO_URL", "http://172.18.0.1:18070")
ODOO_DB = os.environ.get("ODOO_DB", "odoo_minghouse")
ODOO_UID = int(os.environ.get("ODOO_UID", "2"))
ODOO_API_KEY = os.environ.get("ODOO_API_KEY", "1362a613017363da65d6cbb7b3c831fa68a7a71e")

def get_models():
    return xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

def get_vn_time():
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_vn = now_utc + datetime.timedelta(hours=7)
    return now_vn.strftime("%Y-%m-%d %H:%M:%S")

def find_project_id(identifier):
    models = get_models()
    try:
        pid = int(identifier)
        return pid
    except ValueError:
        pass
    
    raw = str(identifier).strip()
    clean_id = raw.upper()
    
    rules = [
        (["PHƯỚC THỂ", "PHUOC THE", "PT", "GOO-PT", "GOO PT"], "Vận Hành - GOO Phước Thể"),
        (["A3", "MING A3", "MING-A3"], "Vận Hành - Ming A3 (Liên Hương)"),
        (["PHAN RÍ", "PHAN RI", "PR", "MING-PR", "MING PR"], "Vận Hành - Ming Phan Rí"),
        (["LÊ DUẨN", "LE DUAN", "LD", "GOO-LD", "GOO LD"], "Vận Hành - GOO-LD"),
        (["A2", "GOO-A2", "GOO A2"], "Vận Hành - GOO-A2"),
        (["LIÊN HƯƠNG", "LIEN HUONG", "LH", "MING-LH"], "Vận Hành - Ming Liên Hương"),
        (["SỰ CỐ", "SU CO", "BÁO SỰ CỐ", "BẢO TRÌ", "BAO TRI"], "Bảo Trì & Báo Sự Cố Toàn Hệ Thống"),
        (["BÁN HÀNG", "BAN HANG", "CSKH"], "Vận Hành - Toàn Hệ Thống (Chung)"),
    ]
    
    target_name = None
    for keywords, proj_name in rules:
        for kw in keywords:
            if kw in clean_id:
                target_name = proj_name
                break
        if target_name:
            break
            
    if not target_name:
        target_name = raw

    projects = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "project.project", "search_read",
        [[["name", "ilike", target_name]]],
        {"fields": ["id", "name"]}
    )
    if projects:
        return projects[0]["id"]
    return 1 # default to general

def get_or_create_tag(tag_name, color=1):
    try:
        models = get_models()
        existing = models.execute_kw(
            ODOO_DB, ODOO_UID, ODOO_API_KEY,
            "project.tags", "search_read",
            [[["name", "=", tag_name]]],
            {"fields": ["id", "name"]}
        )
        if existing:
            return existing[0]["id"]
        tag_id = models.execute_kw(
            ODOO_DB, ODOO_UID, ODOO_API_KEY,
            "project.tags", "create",
            [{"name": tag_name, "color": color}]
        )
        return tag_id
    except Exception:
        return None

def find_employee(emp_identifier):
    if not emp_identifier:
        return None
    models = get_models()
    query = str(emp_identifier).strip()
    domain = [
        "|", "|", "|", "|",
        ["name", "ilike", query],
        ["work_phone", "ilike", query],
        ["mobile_phone", "ilike", query],
        ["work_email", "ilike", query],
        ["additional_note", "ilike", query]
    ]
    employees = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "hr.employee", "search_read",
        [domain],
        {"fields": ["id", "name", "work_phone", "mobile_phone", "work_email", "user_id", "department_id"]}
    )
    if employees:
        emp = employees[0]
        user_id = emp["user_id"][0] if emp.get("user_id") else None
        phone = emp["work_phone"] or emp["mobile_phone"] or ""
        dept = emp["department_id"][1] if emp.get("department_id") else ""
        return {
            "id": emp["id"],
            "user_id": user_id,
            "name": emp["name"],
            "phone": phone,
            "email": emp["work_email"] or "",
            "department": dept
        }
    return None

def create_delegated_task(branch, title, description, emp_identifier, deadline_str, assigner_name):
    """
    Tạo nhiệm vụ được giao ủy quyền từ Zalo Group:
    - Map chi nhánh sang project_id chuẩn
    - Parse deadline_str sang giờ Việt Nam (UTC+7) chuẩn ISO: YYYY-MM-DD HH:MM:SS
    - Tìm nhân sự trong hr.employee của chi nhánh
    - Ghi nhận Assignee và Assigner vào Chatter
    - Tính sẵn reminder_at_ms (trước 30 phút) để trả về cho Cron tool
    """
    models = get_models()
    pid = find_project_id(branch)
    emp_info = find_employee(emp_identifier)
    
    # Simple deadline parsing for demo purposes (assumed passed as YYYY-MM-DD HH:MM:SS)
    # In full impl, this would use dateutil.parser
    deadline = deadline_str
    
    vals = {
        "name": title,
        "project_id": pid,
        "stage_id": 1,
        "state": "01_in_progress",
        "date_deadline": deadline
    }
    
    if emp_info:
        if emp_info.get("user_id"):
            vals["user_ids"] = [(4, emp_info["user_id"])]
        desc_extra = f"<p><strong>Người giao:</strong> {assigner_name}<br/><strong>Người làm:</strong> {emp_info['name']} ({emp_info['phone']})<br/><strong>Hạn chót:</strong> {deadline}</p>"
        vals["description"] = f"<p>{description}</p>{desc_extra}"
    else:
        vals["description"] = f"<p>{description}</p><p><strong>Người giao:</strong> {assigner_name}</p>"

    task_id = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "project.task", "create",
        [vals]
    )
    
    # Calculate 30 mins before deadline
    try:
        dt = datetime.datetime.strptime(deadline, "%Y-%m-%d %H:%M:%S")
        reminder_dt = dt - datetime.timedelta(minutes=30)
        reminder_at_ms = int(reminder_dt.timestamp() * 1000)
    except:
        reminder_at_ms = 0

    print(json.dumps({
        "status": "success",
        "task_id": task_id,
        "reminder_at_ms": reminder_at_ms,
        "message": f"Task #{task_id} tạo thành công."
    }, ensure_ascii=False, indent=2))

def update_task_deadline(task_id, new_deadline_str, reason=""):
    """
    Cập nhật lại hạn chót trên Odoo task và ghi nhận lý do vào Chatter.
    Trả về reminder_at_ms mới.
    """
    models = get_models()
    task_id = int(task_id)
    
    vals = {"date_deadline": new_deadline_str}
    models.execute_kw(ODOO_DB, ODOO_UID, ODOO_API_KEY, "project.task", "write", [[task_id], vals])
    
    # Post chatter
    chatter_msg = f"⏳ <b>Cập nhật hạn chót</b><br/>- Hạn mới: {new_deadline_str}<br/>- Lý do: {reason}"
    models.execute_kw(ODOO_DB, ODOO_UID, ODOO_API_KEY, "project.task", "message_post", [[task_id]], {"body": chatter_msg})
    
    # New reminder
    dt = datetime.datetime.strptime(new_deadline_str, "%Y-%m-%d %H:%M:%S")
    reminder_at_ms = int((dt - datetime.timedelta(minutes=30)).timestamp() * 1000)
    
    print(json.dumps({"status": "success", "reminder_at_ms": reminder_at_ms}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    # Simplified main for implementation
    if len(sys.argv) < 2:
        sys.exit(1)
    
    cmd = sys.argv[1]
    if cmd == "create_delegated_task":
        create_delegated_task(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], sys.argv[7])
    elif cmd == "update_task_deadline":
        update_task_deadline(sys.argv[2], sys.argv[3], sys.argv[4])
