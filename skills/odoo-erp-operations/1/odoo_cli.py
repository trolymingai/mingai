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

def list_branches():
    models = get_models()
    branches = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "ming.branch", "search_read", [[]],
        {"fields": ["id", "name", "code", "brand"]}
    )
    print(json.dumps({"status": "success", "data": branches}, ensure_ascii=False, indent=2))

def list_projects():
    models = get_models()
    projects = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "project.project", "search_read", [[]],
        {"fields": ["id", "name"]}
    )
    print(json.dumps({"status": "success", "data": projects}, ensure_ascii=False, indent=2))

def find_project_id(identifier):
    models = get_models()
    try:
        pid = int(identifier)
        return pid
    except ValueError:
        pass
    
    raw = str(identifier).strip()
    clean_id = raw.upper()
    
    # Priority mapping table
    # Matches branch keywords in group names or branch codes
    rules = [
        # Phước Thể
        (["PHƯỚC THỂ", "PHUOC THE", "PT", "GOO-PT", "GOO PT"], "Vận Hành - GOO Phước Thể"),
        # Ming A3 (Liên Hương)
        (["A3", "MING A3", "MING-A3"], "Vận Hành - Ming A3 (Liên Hương)"),
        # Ming Phan Rí
        (["PHAN RÍ", "PHAN RI", "PR", "MING-PR", "MING PR"], "Vận Hành - Ming Phan Rí"),
        # GOO Lê Duẩn
        (["LÊ DUẨN", "LE DUAN", "LD", "GOO-LD", "GOO LD"], "Vận Hành - GOO-LD"),
        # GOO A2
        (["A2", "GOO-A2", "GOO A2"], "Vận Hành - GOO-A2"),
        # Ming Liên Hương
        (["LIÊN HƯƠNG", "LIEN HUONG", "LH", "MING-LH"], "Vận Hành - Ming Liên Hương"),
        # Sự cố & Bảo trì
        (["SỰ CỐ", "SU CO", "BÁO SỰ CỐ", "BẢO TRÌ", "BAO TRI"], "Bảo Trì & Báo Sự Cố Toàn Hệ Thống"),
        # Bán hàng / Chung
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
    """
    Get or create tag in project.tags.
    Colors in Odoo: 1=Red, 4=Blue, 10=Green, 2=Orange
    """
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

def get_tasks(project_id_or_name=None):
    models = get_models()
    domain = []
    if project_id_or_name:
        pid = find_project_id(project_id_or_name)
        domain.append(["project_id", "=", pid])
    
    tasks = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "project.task", "search_read",
        [domain],
        {"fields": ["id", "name", "project_id", "stage_id", "state", "priority", "user_ids", "create_date", "write_date", "description"], "limit": 20, "order": "id desc"}
    )
    print(json.dumps({"status": "success", "count": len(tasks), "data": tasks}, ensure_ascii=False, indent=2))

def create_task(project_id_or_name, title, description="", emp_identifier=None):
    models = get_models()
    pid = find_project_id(project_id_or_name)
    now_vn = get_vn_time()
    
    vals = {
        "name": title,
        "project_id": pid,
        "stage_id": 1, # Hộp thư đến
        "state": "01_in_progress",
        "priority": "0"
    }
    
    emp_info = find_employee(emp_identifier) if emp_identifier else None
    if emp_info:
        if emp_info.get("user_id"):
            vals["user_ids"] = [(4, emp_info["user_id"])]
        desc_extra = f"<p><strong>Nhân sự phụ trách:</strong> {emp_info['name']} ({emp_info['phone']}) - {emp_info['department']}<br/><strong>Thời gian giao:</strong> {now_vn}</p>"
        vals["description"] = f"<p>{description}</p>{desc_extra}" if description else desc_extra
    else:
        if description:
            vals["description"] = f"<p>{description}</p>"

    task_id = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "project.task", "create",
        [vals]
    )
    
    # Post chatter
    chatter_msg = f"📋 <b>Giao việc / Checklist ca mới</b><br/>- Tiêu đề: {title}<br/>- Thời gian: {now_vn}"
    if emp_info:
        chatter_msg += f"<br/>- Người thực hiện: <b>{emp_info['name']}</b> ({emp_info['phone']})"
    try:
        models.execute_kw(
            ODOO_DB, ODOO_UID, ODOO_API_KEY,
            "project.task", "message_post",
            [[task_id]],
            {"body": chatter_msg, "message_type": "comment"}
        )
    except Exception:
        pass

    print(json.dumps({
        "status": "success",
        "task_id": task_id,
        "title": title,
        "project_id": pid,
        "assigned_to": emp_info["name"] if emp_info else None,
        "message": f"Tạo task #{task_id} thành công trên Odoo ERP."
    }, ensure_ascii=False, indent=2))

def complete_task(task_id, emp_identifier=None, note=""):
    models = get_models()
    task_id = int(task_id)
    now_vn = get_vn_time()
    emp_info = find_employee(emp_identifier) if emp_identifier else None
    
    vals = {
        "stage_id": 6, # Hoàn tất
        "state": "1_done"
    }
    
    tag_ok = get_or_create_tag("Đạt chuẩn", color=10)
    if tag_ok:
        vals["tag_ids"] = [(4, tag_ok)]
    
    if emp_info and emp_info.get("user_id"):
        vals["user_ids"] = [(4, emp_info["user_id"])]
        
    models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "project.task", "write",
        [[task_id], vals]
    )
    
    # Post chatter
    chatter_msg = f"✅ <b>Hoàn tất checklist qua Zalo</b><br/>- Thời gian hoàn tất: {now_vn}"
    if emp_info:
        chatter_msg += f"<br/>- Nhân sự hoàn tất: <b>{emp_info['name']}</b> ({emp_info['phone']})"
    if note:
        chatter_msg += f"<br/>- Ghi chú / Số liệu báo cáo: {note}"
        
    try:
        models.execute_kw(
            ODOO_DB, ODOO_UID, ODOO_API_KEY,
            "project.task", "message_post",
            [[task_id]],
            {"body": chatter_msg, "message_type": "comment"}
        )
    except Exception:
        pass

    print(json.dumps({
        "status": "success",
        "task_id": task_id,
        "completed_by": emp_info["name"] if emp_info else "Nhân viên",
        "message": f"Task #{task_id} đã cập nhật sang trạng thái Hoàn tất trên Odoo ERP."
    }, ensure_ascii=False, indent=2))

def flag_anomaly(task_id_or_branch, title, emp_identifier, reason, metrics=""):
    """
    Flags a task as suspicious or anomalous (Anti-Fraud mechanism):
    - Sets state to '02_changes_requested' (Cần đối soát / Yêu cầu thay đổi)
    - Sets priority to '1' (Cắm sao ưu tiên cảnh báo đỏ)
    - Adds red tag 'Nghi vấn báo ảo'
    - Posts high-visibility alert to Odoo chatter for Store Manager / CEO
    """
    models = get_models()
    now_vn = get_vn_time()
    emp_info = find_employee(emp_identifier) if emp_identifier else None
    emp_name = emp_info["name"] if emp_info else str(emp_identifier)
    
    # Check if first arg is an existing task ID
    task_id = None
    try:
        task_id = int(task_id_or_branch)
    except ValueError:
        pass
        
    tag_fraud = get_or_create_tag("Nghi vấn báo ảo", color=1) # Red tag
    tag_anomaly = get_or_create_tag("Báo cáo bất thường", color=2) # Orange tag
    
    if task_id:
        # Existing task update
        vals = {
            "state": "02_changes_requested",
            "priority": "1"
        }
        tag_commands = []
        if tag_fraud:
            tag_commands.append((4, tag_fraud))
        if tag_anomaly:
            tag_commands.append((4, tag_anomaly))
        if tag_commands:
            vals["tag_ids"] = tag_commands
        if emp_info and emp_info.get("user_id"):
            vals["user_ids"] = [(4, emp_info["user_id"])]
            
        models.execute_kw(ODOO_DB, ODOO_UID, ODOO_API_KEY, "project.task", "write", [[task_id], vals])
    else:
        # Create new flagged task in branch project
        branch = task_id_or_branch
        pid = find_project_id(branch)
        new_vals = {
            "name": f"⚠️ [CẢNH BÁO] {title.strip()}",
            "project_id": pid,
            "stage_id": 1,
            "state": "02_changes_requested",
            "priority": "1",
            "description": f"<p style='color:red;'><strong>CẢNH BÁO BẤT THƯỜNG / NGHI VẤN GIAN LẬN BÁO CÁO</strong></p><p><strong>Nhân sự:</strong> {emp_name}<br/><strong>Lý do:</strong> {reason}<br/><strong>Số liệu ghi nhận:</strong> {metrics}<br/><strong>Thời gian:</strong> {now_vn}</p>"
        }
        tag_commands = []
        if tag_fraud:
            tag_commands.append((4, tag_fraud))
        if tag_anomaly:
            tag_commands.append((4, tag_anomaly))
        if tag_commands:
            new_vals["tag_ids"] = tag_commands
        if emp_info and emp_info.get("user_id"):
            new_vals["user_ids"] = [(4, emp_info["user_id"])]
            
        task_id = models.execute_kw(ODOO_DB, ODOO_UID, ODOO_API_KEY, "project.task", "create", [new_vals])

    # Chatter high-visibility alert
    alert_chatter = (
        f"🚨 <b style='color:#dc3545;'>[CẢNH BÁO BẤT THƯỜNG / NGHI VẤN BÁO ẢO]</b><br/>"
        f"- <b>Nhân sự:</b> {emp_name} ({emp_info['phone'] if emp_info else 'Zalo'})<br/>"
        f"- <b>Hạng mục:</b> {title}<br/>"
        f"- <b>Lý do nghi vấn:</b> <span style='color:#dc3545;'>{reason}</span><br/>"
        f"- <b>Số liệu/Phản hồi:</b> {metrics if metrics else 'Không có hoặc sai chuẩn'}<br/>"
        f"- <b>Thời gian ghi nhận:</b> {now_vn}<br/>"
        f"⚠️ <i>Đề nghị Cửa hàng trưởng kiểm tra lại camera quầy hoặc đối soát thực tế trước khi xác nhận hoàn thành ca.</i>"
    )
    try:
        models.execute_kw(ODOO_DB, ODOO_UID, ODOO_API_KEY, "project.task", "message_post", [[task_id]], {"body": alert_chatter, "message_type": "comment"})
    except Exception:
        pass

    print(json.dumps({
        "status": "flagged",
        "task_id": task_id,
        "title": title,
        "employee": emp_name,
        "state": "02_changes_requested",
        "priority": "1 (Star Alert)",
        "tags": ["Nghi vấn báo ảo", "Báo cáo bất thường"],
        "reason": reason,
        "message": f"Task #{task_id} đã bị CẮM CỜ CẢNH BÁO (Flagged) trên Odoo ERP do nghi vấn gian lận/bất thường."
    }, ensure_ascii=False, indent=2))

def sync_checklist(branch, title, emp_identifier, status="done", note=""):
    """
    High-level smart sync for staff checklist with Anti-Fraud routing:
    - If status is 'flagged', 'suspicious', 'bat_thuong' -> routes to flag_anomaly()
    - If status is 'done' -> searches or creates task, tags 'Đạt chuẩn', records metrics in chatter.
    """
    models = get_models()
    pid = find_project_id(branch)
    emp_info = find_employee(emp_identifier) if emp_identifier else None
    now_vn = get_vn_time()
    
    clean_status = status.lower().strip()
    if clean_status in ["flag", "flagged", "anomaly", "bat_thuong", "nghi_van", "gian_lan"]:
        flag_anomaly(branch, title, emp_identifier, reason=note or "Nghi vấn báo cáo ảo hoặc sai số chuẩn", metrics=note)
        return

    # Search today's task matching title
    existing = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "project.task", "search_read",
        [[["project_id", "=", pid], ["name", "ilike", title.strip()]]],
        {"fields": ["id", "name", "stage_id", "state"], "limit": 1, "order": "id desc"}
    )
    
    tag_ok = get_or_create_tag("Đạt chuẩn", color=10) # Green
    
    if existing:
        task_id = existing[0]["id"]
        vals = {}
        if clean_status in ["done", "hoantat", "hoàn tất", "ok"]:
            vals["stage_id"] = 6 # Hoàn tất
            vals["state"] = "1_done"
            vals["priority"] = "0"
            if tag_ok:
                vals["tag_ids"] = [(4, tag_ok)]
        if emp_info and emp_info.get("user_id"):
            vals["user_ids"] = [(4, emp_info["user_id"])]
            
        if vals:
            models.execute_kw(
                ODOO_DB, ODOO_UID, ODOO_API_KEY,
                "project.task", "write",
                [[task_id], vals]
            )
            
        chatter = f"✅ <b>Checklist ca được đồng bộ từ Zalo</b><br/>- Nhân viên: <b>{emp_info['name'] if emp_info else emp_identifier}</b><br/>- Trạng thái: Hoàn tất<br/>- Thời gian: {now_vn}"
        if note:
            chatter += f"<br/>- Số liệu / Ghi chú xác thực: {note}"
        try:
            models.execute_kw(ODOO_DB, ODOO_UID, ODOO_API_KEY, "project.task", "message_post", [[task_id]], {"body": chatter, "message_type": "comment"})
        except Exception:
            pass
            
        print(json.dumps({
            "status": "success",
            "action": "updated",
            "task_id": task_id,
            "title": existing[0]["name"],
            "branch": branch,
            "employee": emp_info["name"] if emp_info else emp_identifier,
            "stage": "Hoàn tất",
            "message": f"Đã đồng bộ hoàn tất checklist #{task_id} lên Odoo ERP cho {emp_info['name'] if emp_info else emp_identifier}."
        }, ensure_ascii=False, indent=2))
        return
        
    # If not existing, create directly
    is_done = clean_status in ["done", "hoantat", "hoàn tất", "ok"]
    new_vals = {
        "name": title.strip(),
        "project_id": pid,
        "stage_id": 6 if is_done else 1,
        "state": "1_done" if is_done else "01_in_progress",
        "priority": "0",
        "description": f"<p>{note}</p><p><strong>Nhân sự:</strong> {emp_info['name'] if emp_info else emp_identifier}<br/><strong>Thời gian:</strong> {now_vn}</p>"
    }
    if is_done and tag_ok:
        new_vals["tag_ids"] = [(4, tag_ok)]
    if emp_info and emp_info.get("user_id"):
        new_vals["user_ids"] = [(4, emp_info["user_id"])]
        
    task_id = models.execute_kw(ODOO_DB, ODOO_UID, ODOO_API_KEY, "project.task", "create", [new_vals])
    
    chatter = f"✅ <b>Checklist ca mới đồng bộ từ Zalo</b><br/>- Nhân viên: <b>{emp_info['name'] if emp_info else emp_identifier}</b><br/>- Trạng thái: {'Hoàn tất' if is_done else 'Đang xử lý'}<br/>- Thời gian: {now_vn}"
    if note:
        chatter += f"<br/>- Số liệu / Ghi chú xác thực: {note}"
    try:
        models.execute_kw(ODOO_DB, ODOO_UID, ODOO_API_KEY, "project.task", "message_post", [[task_id]], {"body": chatter, "message_type": "comment"})
    except Exception:
        pass

    print(json.dumps({
        "status": "success",
        "action": "created",
        "task_id": task_id,
        "title": title.strip(),
        "branch": branch,
        "employee": emp_info["name"] if emp_info else emp_identifier,
        "stage": "Hoàn tất" if is_done else "Đang xử lý",
        "message": f"Tạo mới và đồng bộ checklist #{task_id} lên Odoo ERP cho {emp_info['name'] if emp_info else emp_identifier}."
    }, ensure_ascii=False, indent=2))

def verify_metrics(metric_type, value_str):
    """
    Validates operational metrics against Ming Coffee F&B Golden Standards:
    - tu_dong: -18.0 to -14.0 C
    - tu_mat: 2.0 to 5.0 C
    - noi_hoi: 1.1 to 1.3 bar
    - chiet_xuat: 8.5 to 9.5 bar
    - shot_time: 25.0 to 30.0 seconds
    - dose_yield: 18.0 - 18.5g in -> 36.0 - 38.0g out
    """
    standards = {
        "tu_dong": {"name": "Nhiệt độ Tủ Đông", "min": -18.0, "max": -14.0, "unit": "°C"},
        "tu_mat": {"name": "Nhiệt độ Tủ Mát Quầy Bar", "min": 2.0, "max": 5.0, "unit": "°C"},
        "noi_hoi": {"name": "Áp suất Nồi hơi (Boiler)", "min": 1.1, "max": 1.3, "unit": "bar"},
        "chiet_xuat": {"name": "Áp suất Chiết xuất (Pump)", "min": 8.5, "max": 9.5, "unit": "bar"},
        "shot_time": {"name": "Thời gian Chiết xuất Espresso", "min": 25.0, "max": 30.0, "unit": "giây"},
        "shot_out": {"name": "Lượng Espresso Chiết xuất", "min": 35.0, "max": 38.0, "unit": "g"}
    }
    
    mtype = metric_type.lower().strip()
    rule = standards.get(mtype)
    if not rule:
        print(json.dumps({
            "status": "error",
            "message": f"Loại thông số '{metric_type}' không tồn tại trong chuẩn quy định. Danh sách chuẩn: {list(standards.keys())}"
        }, ensure_ascii=False, indent=2))
        return

    try:
        val = float(value_str.replace("°C", "").replace("bar", "").replace("g", "").replace("s", "").strip())
    except ValueError:
        print(json.dumps({
            "status": "invalid",
            "valid": False,
            "metric": rule["name"],
            "input": value_str,
            "message": f"Không thể phân tích giá trị số từ '{value_str}'."
        }, ensure_ascii=False, indent=2))
        return

    is_valid = rule["min"] <= val <= rule["max"]
    result = {
        "status": "success",
        "valid": is_valid,
        "metric": rule["name"],
        "input_value": val,
        "standard_range": f"{rule['min']} ~ {rule['max']} {rule['unit']}",
        "message": "Thông số chuẩn xác và đạt tiêu chuẩn chất lượng." if is_valid else f"Thông số BẤT THƯỜNG! Nằm ngoài dải chuẩn an toàn ({rule['min']} ~ {rule['max']} {rule['unit']}). Cần kiểm tra ngay!"
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

def get_staff_tasks(emp_identifier):
    models = get_models()
    emp_info = find_employee(emp_identifier)
    if not emp_info:
        print(json.dumps({"status": "error", "message": f"Không tìm thấy nhân viên: {emp_identifier}"}, ensure_ascii=False, indent=2))
        return
        
    user_id = emp_info.get("user_id")
    if not user_id:
        print(json.dumps({"status": "error", "message": f"Nhân viên {emp_info['name']} chưa liên kết tài khoản Odoo."}, ensure_ascii=False, indent=2))
        return
        
    tasks = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "project.task", "search_read",
        [[["user_ids", "in", [user_id]]]],
        {"fields": ["id", "name", "project_id", "stage_id", "state", "priority", "create_date", "write_date"], "limit": 10, "order": "id desc"}
    )
    print(json.dumps({
        "status": "success",
        "employee": emp_info["name"],
        "phone": emp_info["phone"],
        "tasks_count": len(tasks),
        "data": tasks
    }, ensure_ascii=False, indent=2))

def onboard_employee(name, phone, email, branch_code, work_schedule=""):
    models = get_models()
    existing = find_employee(phone) or find_employee(email)
    if existing:
        print(json.dumps({
            "status": "exists",
            "employee_id": existing["id"],
            "name": existing["name"],
            "message": f"Nhân viên đã tồn tại trên Odoo ERP (ID: {existing['id']})."
        }, ensure_ascii=False, indent=2))
        return

    b_clean = branch_code.upper().strip()
    dept_map = {
        "A3": "Ming A3 (Liên Hương)",
        "MING-A3": "Ming A3 (Liên Hương)",
        "MING A3": "Ming A3 (Liên Hương)",
        "LH": "Ming Liên Hương",
        "MING-LH": "Ming Liên Hương",
        "MING LIÊN HƯƠNG": "Ming Liên Hương",
        "PR": "Ming Phan Rí",
        "MING-PR": "Ming Phan Rí",
        "MING PHAN RÍ": "Ming Phan Rí",
        "LD": "GOO-LD",
        "GOO-LD": "GOO-LD",
        "A2": "GOO-A2",
        "GOO-A2": "GOO-A2"
    }
    target_dept_name = dept_map.get(b_clean, branch_code)
    depts = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "hr.department", "search_read",
        [[["name", "ilike", target_dept_name]]],
        {"fields": ["id", "name"]}
    )
    dept_id = depts[0]["id"] if depts else False
    dept_name = depts[0]["name"] if depts else target_dept_name

    user_vals = {
        "name": name,
        "login": email if email else phone,
        "email": email,
        "groups_id": [(6, 0, [1])]
    }
    try:
        user_id = models.execute_kw(ODOO_DB, ODOO_UID, ODOO_API_KEY, "res.users", "create", [user_vals])
    except Exception:
        users = models.execute_kw(ODOO_DB, ODOO_UID, ODOO_API_KEY, "res.users", "search_read", [[["login", "=", email if email else phone]]], {"fields": ["id"]})
        user_id = users[0]["id"] if users else False

    emp_vals = {
        "name": name,
        "work_phone": phone,
        "mobile_phone": phone,
        "work_email": email,
        "department_id": dept_id,
        "additional_note": f"Lịch làm việc / Ca: {work_schedule}" if work_schedule else "",
    }
    if user_id:
        emp_vals["user_id"] = user_id

    emp_id = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "hr.employee", "create",
        [emp_vals]
    )

    now_vn = get_vn_time()
    chatter_msg = f"🎉 <b>Chào mừng nhân sự mới vào hệ thống Ming Coffee!</b><br/>- Họ tên: <b>{name}</b><br/>- SĐT: {phone}<br/>- Chi nhánh: {dept_name}<br/>- Ca/Lịch làm: {work_schedule}<br/>- Thời gian: {now_vn}"
    try:
        models.execute_kw(ODOO_DB, ODOO_UID, ODOO_API_KEY, "hr.employee", "message_post", [[emp_id]], {"body": chatter_msg, "message_type": "comment"})
    except Exception:
        pass

    print(json.dumps({
        "status": "success",
        "employee_id": emp_id,
        "user_id": user_id,
        "name": name,
        "phone": phone,
        "email": email,
        "department": dept_name,
        "work_schedule": work_schedule,
        "message": f"Tạo hồ sơ nhân viên thành công trên Odoo ERP (ID: {emp_id})."
    }, ensure_ascii=False, indent=2))

def search_employee(query):
    models = get_models()
    query = query.strip()
    domain = ["|", "|", "|", ["name", "ilike", query], ["work_phone", "ilike", query], ["mobile_phone", "ilike", query], ["work_email", "ilike", query]]
    employees = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "hr.employee", "search_read",
        [domain],
        {"fields": ["id", "name", "work_phone", "mobile_phone", "work_email", "department_id", "job_title", "user_id"]}
    )
    print(json.dumps({"status": "success", "count": len(employees), "data": employees}, ensure_ascii=False, indent=2))


def add_recognition(employee_name, reason, tag="Tuyên dương"):
    """
    Ghi nhận hành động tích cực / tuyên dương / điểm cộng vào Chatter hồ sơ nhân sự trên Odoo ERP.
    """
    emp = find_employee(employee_name)
    if not emp:
        print(json.dumps({
            "status": "error",
            "message": f"Không tìm thấy nhân viên '{employee_name}' trên hệ thống Odoo để ghi nhận. Vui lòng kiểm tra lại họ tên hoặc tạo hồ sơ nhân viên trước."
        }, ensure_ascii=False, indent=2))
        return

    models = get_models()
    now_vn = get_vn_time()
    dept = emp.get("department") or "Ming Coffee"
    chatter_body = f"""
    🌟 <b>[ĐIỂM CỘNG - TUYÊN DƯƠNG CA LÀM VIỆC]</b><br/>
    - <b>Nhân sự:</b> {emp['name']}<br/>
    - <b>Chi nhánh:</b> {dept}<br/>
    - <b>Phân loại:</b> {tag}<br/>
    - <b>Hành động ghi nhận:</b> {reason}<br/>
    - <b>Thời gian ghi nhận:</b> {now_vn}<br/>
    - <b>Người ghi nhận:</b> Ban Điều Hành / CEO
    """
    try:
        msg_id = models.execute_kw(
            ODOO_DB, ODOO_UID, ODOO_API_KEY,
            "hr.employee", "message_post",
            [[emp["id"]]],
            {"body": chatter_body, "message_type": "comment", "subtype_xmlid": "mail.mt_comment"}
        )
        print(json.dumps({
            "status": "success",
            "employee_id": emp["id"],
            "employee_name": emp["name"],
            "department": dept,
            "message_id": msg_id,
            "message": f"Đã cập nhật điểm cộng và tuyên dương vào hồ sơ nhân sự của {emp['name']} trên hệ thống Odoo thành công."
        }, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({
            "status": "error",
            "message": f"Lỗi khi gửi ghi nhận lên Odoo: {str(e)}"
        }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: odoo_cli <command> [args...]")
        print("Commands:")
        print("  list_branches")
        print("  list_projects")
        print("  get_tasks [project_id_or_branch]")
        print("  create_task <branch/project> <title> [desc] [employee]")
        print("  complete_task <task_id> [employee] [note]")
        print("  sync_checklist <branch> <title> <employee> [status] [note]")
        print("  flag_anomaly <branch_or_task_id> <title> <employee> <reason> [metrics]")
        print("  verify_metrics <metric_type> <value>")
        print("  get_staff_tasks <employee>")
        print("  onboard_employee <name> <phone> <email> <branch> [schedule]")
        print("  search_employee <query>")
        print("  add_recognition <employee> <reason> [tag]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "list_branches":
        list_branches()
    elif cmd == "list_projects":
        list_projects()
    elif cmd == "get_tasks" or cmd in ["get_branch_status", "branch_status"]:
        pid = sys.argv[2] if len(sys.argv) > 2 else None
        get_tasks(pid)
    elif cmd == "create_task":
        if len(sys.argv) < 4:
            print("Error: create_task requires <project/branch> <title> [desc] [employee]")
            sys.exit(1)
        desc = sys.argv[4] if len(sys.argv) > 4 else ""
        emp = sys.argv[5] if len(sys.argv) > 5 else None
        create_task(sys.argv[2], sys.argv[3], desc, emp)
    elif cmd == "complete_task":
        if len(sys.argv) < 3:
            print("Error: complete_task requires <task_id> [employee] [note]")
            sys.exit(1)
        emp = sys.argv[3] if len(sys.argv) > 3 else None
        note = sys.argv[4] if len(sys.argv) > 4 else ""
        complete_task(sys.argv[2], emp, note)
    elif cmd == "flag_anomaly":
        if len(sys.argv) < 6:
            print("Error: flag_anomaly requires <branch_or_task_id> <title> <employee> <reason> [metrics]")
            sys.exit(1)
        metrics = sys.argv[6] if len(sys.argv) > 6 else ""
        flag_anomaly(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], metrics)
    elif cmd == "verify_metrics":
        if len(sys.argv) < 4:
            print("Error: verify_metrics requires <metric_type> <value>")
            sys.exit(1)
        verify_metrics(sys.argv[2], sys.argv[3])
    elif cmd == "sync_checklist":
        if len(sys.argv) < 5:
            print("Error: sync_checklist requires <branch> <title> <employee> [status] [note]")
            sys.exit(1)
        status = sys.argv[5] if len(sys.argv) > 5 else "done"
        note = sys.argv[6] if len(sys.argv) > 6 else ""
        sync_checklist(sys.argv[2], sys.argv[3], sys.argv[4], status, note)
    elif cmd == "get_staff_tasks":
        if len(sys.argv) < 3:
            print("Error: get_staff_tasks requires <employee>")
            sys.exit(1)
        get_staff_tasks(sys.argv[2])
    elif cmd == "onboard_employee":
        if len(sys.argv) < 6:
            print("Error: onboard_employee requires <name> <phone> <email> <branch> [schedule]")
            sys.exit(1)
        sched = sys.argv[6] if len(sys.argv) > 6 else ""
        onboard_employee(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sched)
    elif cmd == "add_recognition":
        if len(sys.argv) < 4:
            print("Error: add_recognition requires <employee> <reason> [tag]")
            sys.exit(1)
        tag = sys.argv[4] if len(sys.argv) > 4 else "Tuyên dương"
        add_recognition(sys.argv[2], sys.argv[3], tag)
    elif cmd == "search_employee":
        if len(sys.argv) < 3:
            print("Error: search_employee requires <query>")
            sys.exit(1)
        search_employee(sys.argv[2])
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
