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
        "GOO-A2": "GOO-A2",
        "PT": "Chi nhánh GOO Phước Thể",
        "GOO-PT": "Chi nhánh GOO Phước Thể",
        "GOO PT": "Chi nhánh GOO Phước Thể",
        "PHƯỚC THỂ": "Chi nhánh GOO Phước Thể",
        "PHUOC THE": "Chi nhánh GOO Phước Thể"
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


def check_shift_compliance(branch, shift_type="open"):
    """
    Kiểm tra xem ca làm việc hôm nay của chi nhánh đã hoàn tất checklist và gửi số liệu chưa.
    shift_type: 'open' (Mở ca 06:30) hoặc 'close' (Đóng ca 22:00).
    """
    models = get_models()
    pid = find_project_id(branch)
    today = datetime.date.today().strftime("%Y-%m-%d")
    
    title_keyword = "Mở Ca" if str(shift_type).lower() in ["open", "mở ca", "mo_ca", "sang"] else "Đóng Ca"
    
    tasks = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "project.task", "search_read",
        [[["project_id", "=", pid], ["name", "ilike", title_keyword], ["create_date", ">=", today]]],
        {"fields": ["id", "name", "stage_id", "state", "user_ids", "write_date", "description"], "limit": 1}
    )
    
    if not tasks:
        print(json.dumps({
            "status": "missing",
            "branch": branch,
            "shift_type": shift_type,
            "message": f"Chưa có báo cáo checklist {title_keyword} cho chi nhánh {branch} hôm nay ({today})."
        }, ensure_ascii=False, indent=2))
        return False
        
    t = tasks[0]
    is_done = t.get("state") == "1_done"
    print(json.dumps({
        "status": "completed" if is_done else "in_progress",
        "task_id": t["id"],
        "title": t["name"],
        "branch": branch,
        "shift_type": shift_type,
        "is_done": is_done,
        "assigned_user": t.get("user_ids"),
        "last_update": t.get("write_date"),
        "message": f"Checklist {title_keyword} của {branch} hiện đang: {'ĐÃ HOÀN TẤT' if is_done else 'ĐANG XỬ LÝ (CHƯA HOÀN TẤT)'}."
    }, ensure_ascii=False, indent=2))
    return is_done

def escalate_shift(branch, shift_type="open", level="1", reason=""):
    """
    Kích hoạt ma trận leo thang (Escalation Matrix) cho ca làm việc bị trễ:
    - Level 1 (Nhắc nhở ca trực - T+15m): Tạo/Ghi chú task Odoo, yêu cầu khẩn cấp nộp số liệu.
    - Level 2 (Báo động CHT - T+30m): Set Priority=1 (High), Stage=Changes Requested/Warning, ghi cảnh báo đỏ.
    - Level 3 (Báo động CEO - T+45m): Cắm cờ Anomaly, ghi nhận biên bản vi phạm vận hành lên Odoo.
    """
    models = get_models()
    pid = find_project_id(branch)
    today = datetime.date.today().strftime("%Y-%m-%d")
    now_vn = get_vn_time()
    
    title_keyword = "Mở Ca" if str(shift_type).lower() in ["open", "mở ca", "mo_ca", "sang"] else "Đóng Ca"
    task_title = f"Checklist {title_keyword} - {branch} - {today}"
    
    tasks = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "project.task", "search_read",
        [[["project_id", "=", pid], ["name", "ilike", title_keyword], ["create_date", ">=", today]]],
        {"fields": ["id", "name", "stage_id", "state", "priority"], "limit": 1}
    )
    
    lvl = str(level).strip()
    tag_name = f"Leo thang Level {lvl}"
    tag_id = get_or_create_tag(tag_name, color=1 if lvl in ["2", "3"] else 2)
    
    if tasks:
        task_id = tasks[0]["id"]
    else:
        new_task = {
            "name": task_title,
            "project_id": pid,
            "stage_id": 1,
            "state": "01_in_progress",
            "priority": "1" if lvl in ["2", "3"] else "0",
            "description": f"<p>Tự động tạo từ ma trận leo thang trễ hạn {title_keyword}.</p>"
        }
        task_id = models.execute_kw(ODOO_DB, ODOO_UID, ODOO_API_KEY, "project.task", "create", [new_task])
        
    write_vals = {"priority": "1" if lvl in ["2", "3"] else "0"}
    if tag_id:
        write_vals["tag_ids"] = [(4, tag_id)]
    models.execute_kw(ODOO_DB, ODOO_UID, ODOO_API_KEY, "project.task", "write", [[task_id], write_vals])
    
    chatter_msg = f"""
    ⚠️ <b>[CẢNH BÁO LEO THANG VẬN HÀNH - LEVEL {lvl}]</b><br/>
    - <b>Hạng mục:</b> {task_title}<br/>
    - <b>Mức độ:</b> Level {lvl} ({'Nhắc nhở ca trực' if lvl == '1' else 'Báo động CHT' if lvl == '2' else 'Báo cáo CEO vi phạm'})<br/>
    - <b>Lý do:</b> {reason or 'Quá hạn checklist nhưng chưa có số liệu / bằng chứng hoàn tất'}<br/>
    - <b>Thời gian:</b> {now_vn}
    """
    try:
        models.execute_kw(ODOO_DB, ODOO_UID, ODOO_API_KEY, "project.task", "message_post", [[task_id]], {"body": chatter_msg, "message_type": "comment"})
    except Exception:
        pass
        
    print(json.dumps({
        "status": "success",
        "action": "escalated",
        "level": lvl,
        "task_id": task_id,
        "branch": branch,
        "message": f"Đã kích hoạt leo thang Level {lvl} thành công cho {branch} trên Odoo ERP."
    }, ensure_ascii=False, indent=2))


def log_hr_pulse(branch, employee_name, pillar, sentiment, content, is_confidential=False):
    models = get_models()
    now_vn = get_vn_time()
    emp = find_employee(employee_name) if employee_name and str(employee_name).lower() != "ẩn danh" else None
    
    pillar_map = {
        "A": "Trục A: Công bằng & Minh bạch (Phân ca / Thưởng phạt / Thông báo)",
        "B": "Trục B: Hành xử & Lắng nghe (Tôn trọng lúc đông khách / Phản hồi)",
        "C": "Trục C: Làm gương văn hóa (Đúng hẹn / Nhận lỗi / Chuẩn công thức)",
        "D": "Trục D: Vận hành & Kèm cặp (Ca trơn tru / Hướng dẫn đào tạo)",
        "E": "Trục E: Quan hệ đội ngũ (Tương trợ / Hòa nhập / Giải quyết mâu thuẫn)",
        "T": "Trục T: Cảm nhận & Gắn kết chung"
    }
    pillar_desc = pillar_map.get(str(pillar).upper(), pillar)
    confidential_badge = "🔒 [BẢO MẬT - CHRO & CEO]" if is_confidential else "🌱 [CHIA SẺ NỘI BỘ - HR & CHT]"
    emp_label = emp["name"] if emp else (employee_name or "Nhân viên ẩn danh")
    
    chatter_body = (
        f"💬 <b>[NHỊP ĐẬP NHÂN SỰ - HR PULSE & GÓC NHÌN BỊ THIẾU]</b><br/>"
        f"- <b>Chi nhánh:</b> {branch}<br/>"
        f"- <b>Nhân sự:</b> {emp_label}<br/>"
        f"- <b>Chủ đề:</b> {pillar_desc}<br/>"
        f"- <b>Mức độ hài lòng / Đánh giá:</b> {sentiment}<br/>"
        f"- <b>Góc nhìn / Ý kiến chia sẻ:</b> {content}<br/>"
        f"- <b>Phân quyền xem:</b> {confidential_badge}<br/>"
        f"- <b>Thời gian ghi nhận:</b> {now_vn}<br/>"
        f"- <b>Kênh tiếp nhận:</b> Ming AI (Giám đốc Nhân sự & HRBP)"
    )
    
    logged_target = []
    if emp:
        try:
            models.execute_kw(
                ODOO_DB, ODOO_UID, ODOO_API_KEY,
                "hr.employee", "message_post",
                [[emp["id"]]],
                {"body": chatter_body, "message_type": "comment", "subtype_xmlid": "mail.mt_comment"}
            )
            logged_target.append(f"Hồ sơ nhân viên {emp['name']}")
        except Exception:
            pass

    pid = find_project_id(branch)
    try:
        tag_id = get_or_create_tag("HR Pulse", color=4)
        task_data = {
            "name": f"[HR Insight] {str(pillar_desc)[:25]} - {branch}",
            "project_id": pid,
            "description": chatter_body,
            "tag_ids": [(6, 0, [tag_id])] if tag_id else False
        }
        task_id = models.execute_kw(
            ODOO_DB, ODOO_UID, ODOO_API_KEY,
            "project.task", "create",
            [task_data]
        )
        logged_target.append(f"Dự án Odoo (Task #{task_id})")
    except Exception:
        pass

    print(json.dumps({
        "status": "success",
        "branch": branch,
        "employee": emp_label,
        "pillar": pillar_desc,
        "sentiment": sentiment,
        "logged_to": logged_target,
        "message": f"Đã ghi nhận góc nhìn nhân sự thành công lên Odoo ERP: {', '.join(logged_target)}."
    }, ensure_ascii=False, indent=2))

def flag_hr_alert(branch, employee_name, reason, details):
    models = get_models()
    now_vn = get_vn_time()
    pid = find_project_id(branch)
    tag_id = get_or_create_tag("BÁO ĐỘNG ĐỎ NHÂN SỰ", color=1)
    
    alert_body = (
        f"🚨 <b>[BÁO ĐỘNG ĐỎ NHÂN SỰ - BÁO CÁO MẬT CEO DƯƠNG VƯƠNG MINH]</b><br/>"
        f"- <b>Chi nhánh:</b> {branch}<br/>"
        f"- <b>Nhân sự phản ánh:</b> {employee_name}<br/>"
        f"- <b>Vấn đề nghiêm trọng:</b> {reason}<br/>"
        f"- <b>Chi tiết sự việc:</b> {details}<br/>"
        f"- <b>Thời gian:</b> {now_vn}<br/>"
        f"- <b>Đề xuất xử lý:</b> Giám đốc Nhân sự & CEO can thiệp trực tiếp bảo vệ nhân viên."
    )
    try:
        task_data = {
            "name": f"🚨 [BÁO ĐỘNG ĐỎ CEO] {reason} - {branch}",
            "project_id": pid,
            "priority": "1",
            "description": alert_body,
            "tag_ids": [(6, 0, [tag_id])] if tag_id else False
        }
        task_id = models.execute_kw(
            ODOO_DB, ODOO_UID, ODOO_API_KEY,
            "project.task", "create",
            [task_data]
        )
        print(json.dumps({
            "status": "success",
            "task_id": task_id,
            "branch": branch,
            "reason": reason,
            "message": f"Đã cắm cờ báo động đỏ nhân sự #{task_id} thành công lên Odoo ERP và sẵn sàng gửi thông báo khẩn tới CEO."
        }, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({
            "status": "error",
            "message": f"Lỗi cắm cờ báo động đỏ nhân sự: {str(e)}"
        }, ensure_ascii=False, indent=2))

def send_monthly_survey(branch="all"):
    form_url = "https://forms.gle/XGgiUNE3ctf3BaD98"
    msg_lines = [
        "🌟 [KHẢO SÁT THÁNG: MÔI TRƯỜNG LÀM VIỆC TẠI CỬA HÀNG - MING COFFEE]",
        "",
        "Chào cả nhà mình ơi! ✨",
        "Hôm nay là ngày 25, thời điểm để toàn thể đội ngũ cùng nhìn lại 1 tháng vừa qua nhằm giúp cửa hàng mình ngày càng ấm áp, công bằng và trơn tru hơn.",
        "",
        "Khảo sát này HOÀN TOÀN ẨN DANH (không thu email, không hỏi tên hay ca làm).",
        "Kết quả dùng để công ty và anh Minh kịp thời hỗ trợ các anh/chị Cửa Hàng Trưởng nâng cao năng lực quản lý và tháo gỡ những khó khăn cho các bạn trong quầy.",
        "",
        "👉 Mất khoảng 3 phút, cả nhà cùng vào chia sẻ thật lòng nhé:",
        form_url,
        "",
        "🌱 'Sự thật bạn chia sẻ giúp cửa hàng tốt hơn cho chính bạn và đồng đội. Tử tế từ việc nhỏ nhất là cốt lõi của Ming.'"
    ]
    msg = chr(10).join(msg_lines)
    print(json.dumps({
        "status": "success",
        "branch": branch,
        "form_url": form_url,
        "message": msg
    }, ensure_ascii=False, indent=2))

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

def daily_task_report():
    models = get_models()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_vn = now_utc + datetime.timedelta(hours=7)
    today_str = now_vn.strftime("%d/%m/%Y")
    today_start_vn = now_vn.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_vn - datetime.timedelta(hours=7)
    today_start_str = today_start_utc.strftime("%Y-%m-%d %H:%M:%S")

    tasks = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "project.task", "search_read",
        [["|",
          ["create_date", ">=", today_start_str],
          ["state", "in", ["01_in_progress", "02_changes_requested"]]
        ]],
        {"fields": ["id", "name", "project_id", "stage_id", "state", "create_date", "user_ids", "date_deadline"]}
    )
    
    by_project = {}
    completed_count = 0
    in_progress_count = 0
    for t in tasks:
        pname = t["project_id"][1] if t["project_id"] else "Chung"
        if pname not in by_project:
            by_project[pname] = []
        is_done = t.get("state") in ["1_done", "done"] or (t.get("stage_id") and "Hoàn tất" in t["stage_id"][1])
        if is_done:
            completed_count += 1
        else:
            in_progress_count += 1
        by_project[pname].append({
            "id": t["id"],
            "name": t["name"],
            "state": "DONE" if is_done else "IN_PROGRESS"
        })

    report_data = {
        "date": today_str,
        "total_active": len(tasks),
        "completed": completed_count,
        "in_progress": in_progress_count,
        "branches": by_project
    }
    print(json.dumps({"status": "success", "data": report_data}, ensure_ascii=False, indent=2))


def record_uniform_check(branch, shift_type, shift_leader, good_staff_list, violated_staff_list="", notes=""):
    models = get_models()
    pid = find_project_id(branch)
    now_vn = get_vn_time()
    today_vn = now_vn.split()[0]
    
    tag_ok = get_or_create_tag("Đồng phục chuẩn", color=10)
    tag_violation = get_or_create_tag("Vi phạm tác phong", color=1)
    
    clean_viol = str(violated_staff_list or "").strip().lower()
    has_violation = bool(clean_viol and clean_viol not in ["không", "khong", "none", "0", "ko", "chưa", "chua"])
    
    title = f"[Tác phong {shift_type} {today_vn}] {branch}"
    
    desc = "<h3>Giám Sát Tác Phong & Đồng Phục Đầu Ca</h3>"
    desc += "<ul>"
    desc += f"<li><b>Chi nhánh:</b> {branch}</li>"
    desc += f"<li><b>Ca làm việc:</b> {shift_type}</li>"
    desc += f"<li><b>Ca trưởng / CHT giám sát:</b> {shift_leader}</li>"
    desc += f"<li><b>Thời gian kiểm tra:</b> {now_vn}</li>"
    desc += f"<li><b>Nhân sự chuẩn chỉnh (Đạt):</b> <span style='color: green;'>{good_staff_list or 'Toàn ca'}</span></li>"
    viol_txt = violated_staff_list if has_violation else 'Không có (100% đạt chuẩn)'
    desc += f"<li><b>Nhân sự chưa đạt / vi phạm:</b> <span style='color: red;'>{viol_txt}</span></li>"
    desc += "</ul>"
    if notes:
        desc += f"<p><b>Ghi chú hỗ trợ / xử lý tại chỗ:</b> {notes}</p>"
        
    tag_ids = [tag_ok] if not has_violation else [tag_violation]
    
    vals = {
        "name": title,
        "project_id": pid,
        "stage_id": 6 if not has_violation else 1,
        "state": "1_done" if not has_violation else "01_in_progress",
        "priority": "0" if not has_violation else "1",
        "description": desc,
        "tag_ids": [(4, tid) for tid in tag_ids if tid]
    }
    
    task_id = models.execute_kw(ODOO_DB, ODOO_UID, ODOO_API_KEY, "project.task", "create", [vals])
    
    chatter = "👔 <b>Báo cáo tác phong đồng phục đầu ca</b><br/>"
    chatter += f"- Ca trưởng: <b>{shift_leader}</b><br/>"
    chatter += f"- Đạt chuẩn: {good_staff_list or '100% ca'}<br/>"
    if has_violation:
        chatter += f"- ⚠️ Vi phạm: <b>{violated_staff_list}</b> (Đã nhắc nhở)<br/>"
    try:
        models.execute_kw(ODOO_DB, ODOO_UID, ODOO_API_KEY, "project.task", "message_post", [[task_id]], {"body": chatter, "message_type": "comment"})
    except Exception:
        pass
        
    print(json.dumps({
        "status": "success",
        "task_id": task_id,
        "branch": branch,
        "shift": shift_type,
        "has_violation": has_violation,
        "message": f"Đã ghi nhận tác phong ca {shift_type} của {branch} vào Task #{task_id} trên Odoo ERP."
    }, ensure_ascii=False, indent=2))


def uniform_monthly_report(month_str=None):
    models = get_models()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_vn = now_utc + datetime.timedelta(hours=7)
    
    if not month_str:
        month_start = now_vn.replace(day=1, hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
        month_label = now_vn.strftime("%m/%Y")
    else:
        m, y = month_str.split('/')
        month_start = f"{y}-{m}-01 00:00:00"
        month_label = month_str

    tasks = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "project.task", "search_read",
        [[["name", "ilike", "[Tác phong"], ["create_date", ">=", month_start]]],
        {"fields": ["id", "name", "project_id", "tag_ids", "description", "create_date"]}
    )
    
    total_checks = len(tasks)
    violations = []
    by_branch = {}
    
    for t in tasks:
        pname = t["project_id"][1] if t["project_id"] else "Chung"
        if pname not in by_branch:
            by_branch[pname] = {"total": 0, "violations": 0}
        by_branch[pname]["total"] += 1
        
        desc = t.get("description") or ""
        if "Vi phạm:" in desc or "chưa đạt / vi phạm:</span> Không có" not in desc:
            by_branch[pname]["violations"] += 1
            violations.append({
                "task_id": t["id"],
                "branch": pname,
                "title": t["name"],
                "date": t["create_date"]
            })
            
    rate = f"{(total_checks - len(violations)) * 100 / total_checks:.1f}%" if total_checks > 0 else "100%"
    res = {
        "month": month_label,
        "total_shifts_checked": total_checks,
        "total_violations": len(violations),
        "compliance_rate": rate,
        "branch_summary": by_branch,
        "violations": violations
    }
    print(json.dumps({"status": "success", "data": res}, ensure_ascii=False, indent=2))




def register_branch_manager(branch_str, manager_name, role="Quản lý", zalo_name="", zalo_uid=""):
    """
    Registers or updates the Manager / Store Manager (CHT) for a specific branch.
    Saves to /opt/goclaw/branch_managers.json and updates Odoo ming.branch if applicable.
    """
    import json
    import os
    
    registry_file = "/opt/goclaw/branch_managers.json"
    data = {}
    if os.path.exists(registry_file):
        try:
            with open(registry_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
            
    if "branches" not in data:
        data["branches"] = {}
        
    branch_key = branch_str.strip().upper()
    now_str = get_vn_time()
    
    # Try resolving branch on Odoo
    odoo_branch_id = None
    odoo_branch_name = branch_str
    try:
        models = get_models()
        branches = models.execute_kw(
            ODOO_DB, ODOO_UID, ODOO_API_KEY,
            "ming.branch", "search_read", [[]],
            {"fields": ["id", "name", "code", "manager_id"]}
        )
        for b in branches:
            b_name = (b.get("name") or "").upper()
            b_code = (b.get("code") or "").upper()
            if branch_key in b_name or branch_key in b_code or b_name in branch_key:
                odoo_branch_id = b["id"]
                odoo_branch_name = b["name"]
                break
                
        # If branch found, check if manager exists in res.users
        if odoo_branch_id:
            users = models.execute_kw(
                ODOO_DB, ODOO_UID, ODOO_API_KEY,
                "res.users", "search_read",
                [[("name", "ilike", manager_name.strip())]],
                {"fields": ["id", "name"], "limit": 1}
            )
            if users:
                user_id = users[0]["id"]
                models.execute_kw(
                    ODOO_DB, ODOO_UID, ODOO_API_KEY,
                    "ming.branch", "write",
                    [[odoo_branch_id], {"manager_id": user_id}]
                )
    except Exception as e:
        pass

    record = {
        "branch_input": branch_str,
        "branch_name": odoo_branch_name,
        "odoo_branch_id": odoo_branch_id,
        "manager_name": manager_name.strip(),
        "role": role.strip(),
        "zalo_name": zalo_name.strip(),
        "zalo_uid": str(zalo_uid).strip() if zalo_uid else "",
        "updated_at": now_str
    }
    
    data["branches"][branch_key] = record
    if odoo_branch_name != branch_key:
        data["branches"][odoo_branch_name.upper()] = record
        
    with open(registry_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    print(json.dumps({
        "status": "success",
        "message": f"Đã ghi nhận thành công {manager_name} là {role} tại chi nhánh {odoo_branch_name}",
        "data": record
    }, ensure_ascii=False, indent=2))

def get_branch_managers():
    """
    Returns all registered branch managers.
    """
    import json
    import os
    registry_file = "/opt/goclaw/branch_managers.json"
    if os.path.exists(registry_file):
        try:
            with open(registry_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(json.dumps({"status": "success", "data": data.get("branches", {})}, ensure_ascii=False, indent=2))
            return
        except Exception as e:
            pass
    print(json.dumps({"status": "success", "data": {}}, ensure_ascii=False, indent=2))



def get_branch_roster(branch_str):
    """
    Returns list of employees assigned to a specific branch/department.
    """
    import json
    models = get_models()
    clean_b = branch_str.strip().upper()
    
    # Search department
    depts = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "hr.department", "search_read", [[]],
        {"fields": ["id", "name"]}
    )
    target_dept_id = None
    target_dept_name = ""
    for d in depts:
        d_name = d["name"].upper()
        if clean_b in d_name or any(k in d_name for k in clean_b.split()):
            target_dept_id = d["id"]
            target_dept_name = d["name"]
            break
            
    domain = []
    if target_dept_id:
        domain = [("department_id", "=", target_dept_id)]
    else:
        domain = [("name", "ilike", branch_str)]
        
    emps = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "hr.employee", "search_read",
        [domain],
        {"fields": ["id", "name", "job_title", "work_email", "work_phone", "department_id", "user_id"]}
    )
    print(json.dumps({
        "status": "success",
        "branch": target_dept_name or branch_str,
        "total_employees": len(emps),
        "data": emps
    }, ensure_ascii=False, indent=2))

def attendance_check_in(emp_identifier, check_in_time=None):
    """
    Records Check-in for an employee in hr.attendance on Odoo.
    """
    import json
    models = get_models()
    emp_info = find_employee(emp_identifier)
    if not emp_info:
        print(json.dumps({"status": "error", "message": f"Không tìm thấy nhân viên: {emp_identifier}"}, ensure_ascii=False))
        return
        
    now_vn = check_in_time or get_vn_time()
    # Check if already checked in without checkout
    existing = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "hr.attendance", "search_read",
        [[("employee_id", "=", emp_info["id"]), ("check_out", "=", False)]],
        {"fields": ["id", "check_in"], "limit": 1}
    )
    if existing:
        print(json.dumps({
            "status": "warning",
            "message": f"Nhân sự {emp_info['name']} đã check-in trước đó lúc {existing[0]['check_in']}",
            "attendance_id": existing[0]["id"]
        }, ensure_ascii=False, indent=2))
        return

    # Odoo datetime expects UTC
    # Local VN is UTC+7, so convert to UTC for Odoo storage
    dt_local = datetime.datetime.strptime(now_vn, "%Y-%m-%d %H:%M:%S")
    dt_utc = dt_local - datetime.timedelta(hours=7)
    utc_str = dt_utc.strftime("%Y-%m-%d %H:%M:%S")

    att_id = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "hr.attendance", "create",
        [{
            "employee_id": emp_info["id"],
            "check_in": utc_str
        }]
    )
    print(json.dumps({
        "status": "success",
        "message": f"Đã ghi nhận Check-in cho {emp_info['name']} lúc {now_vn}",
        "attendance_id": att_id,
        "employee": emp_info["name"],
        "check_in": now_vn
    }, ensure_ascii=False, indent=2))

def attendance_check_out(emp_identifier, check_out_time=None):
    """
    Records Check-out for an employee in hr.attendance on Odoo.
    """
    import json
    models = get_models()
    emp_info = find_employee(emp_identifier)
    if not emp_info:
        print(json.dumps({"status": "error", "message": f"Không tìm thấy nhân viên: {emp_identifier}"}, ensure_ascii=False))
        return
        
    now_vn = check_out_time or get_vn_time()
    # Find active check-in
    existing = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "hr.attendance", "search_read",
        [[("employee_id", "=", emp_info["id"]), ("check_out", "=", False)]],
        {"fields": ["id", "check_in"], "limit": 1}
    )
    if not existing:
        print(json.dumps({
            "status": "error",
            "message": f"Không tìm thấy lượt Check-in đang mở cho {emp_info['name']}"
        }, ensure_ascii=False, indent=2))
        return

    dt_local = datetime.datetime.strptime(now_vn, "%Y-%m-%d %H:%M:%S")
    dt_utc = dt_local - datetime.timedelta(hours=7)
    utc_str = dt_utc.strftime("%Y-%m-%d %H:%M:%S")

    att_id = existing[0]["id"]
    models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "hr.attendance", "write",
        [[att_id], {"check_out": utc_str}]
    )
    
    # Read back worked_hours
    updated = models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_API_KEY,
        "hr.attendance", "read",
        [[att_id]],
        {"fields": ["worked_hours", "check_in", "check_out"]}
    )
    hours = updated[0].get("worked_hours", 0) if updated else 0
    print(json.dumps({
        "status": "success",
        "message": f"Đã ghi nhận Check-out cho {emp_info['name']} lúc {now_vn}. Tổng giờ làm: {hours:.2f} giờ",
        "attendance_id": att_id,
        "employee": emp_info["name"],
        "check_out": now_vn,
        "worked_hours": hours
    }, ensure_ascii=False, indent=2))


def get_daily_hr_pulse_message(branch="Ming Coffee"):
    now_vn = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)
    weekday = now_vn.weekday()
    
    prompts = {
        0: [
            "Chào cả nhà ca sáng đầu tuần! ✨",
            f"Lịch ca tuần mới tại {branch} các bạn thấy CHT sắp xếp đã thuận tiện việc học và việc riêng của mình chưa nè? Có bạn nào bị trùng lịch hay cần hỗ trợ đổi ca cứ nhắn Ming hoặc báo CHT sớm nha!",
            "",
            "🌱 'Tử tế và minh bạch từ những điều nhỏ nhất là cốt lõi của Ming.'"
        ],
        1: [
            "Ca trưa nay cả nhà mình thế nào rồi nè? ✨",
            f"Lúc cao điểm đông khách vừa rồi, quầy {branch} phối hợp nhịp nhàng chứ? Có lúc nào các bạn cảm thấy hơi ngợp hay áp lực ở khâu nào cần CHT hỗ trợ thêm không?",
            "",
            "✨ 'Bình tĩnh và tôn trọng nhau trong từng giây phút phục vụ.'"
        ],
        2: [
            "Chào buổi chiều cả nhà mình! ✨",
            f"Mấy ngày nay các bạn mới onboard tại {branch} đã quen tay với máy pha và quy trình chưa nè? Có thao tác nào còn bỡ ngỡ cần anh/chị CHT hoặc đồng đội chỉ thêm mẹo không, cứ thoải mái chia sẻ nhé!",
            "",
            "🌱 'Kèm cặp và cùng nhau tiến bộ mỗi ngày.'"
        ],
        3: [
            "Cả nhà ơi, trưa nay đứng quầy có điều gì vui không nè? ✨",
            f"Hôm nay bạn có thấy hành động nào của đồng đội hoặc anh/chị CHT tại {branch} khiến bạn thấy ấn tượng, chú tâm và tự hào không? Cùng thả nhẹ 1 lời khen để tiếp thêm năng lượng cho ca chiều nhé!",
            "",
            "✨ 'Chú tâm từng việc nhỏ để tạo nên tách cà phê tuyệt hảo.'"
        ],
        4: [
            "Cuối tuần sắp tới rồi cả nhà ơi! ✨",
            f"Lượng khách cuối tuần sẽ đông hơn, đội ngũ {branch} mình đã chuẩn bị tinh thần và nguyên liệu sẵn sàng 'chiến' chưa? Ca mình cần hỗ trợ hoặc phối hợp thêm điều gì để chạy ca thật trơn tru không nè?",
            "",
            "🌱 'Đồng đội là điểm tựa - Cùng nhau vượt qua mọi giờ cao điểm.'"
        ],
        5: [
            "Thứ Bảy vui vẻ nha cả nhà! ✨",
            f"Hôm nay quán đông, các bạn nhớ uống đủ nước và giữ nụ cười thật tươi nha. Có tình huống khách khó xử nào cần CHT đứng ra hỗ trợ thì nhớ ới CHT ngay nhé!",
            "",
            "✨ 'Sự hài lòng của khách hàng bắt đầu từ nụ cười của chính các bạn.'"
        ],
        6: [
            "Chủ Nhật rồi, một tuần làm việc sắp khép lại! ✨",
            f"Nhìn lại 1 tuần vừa qua đứng quầy tại {branch}, điều gì làm bạn cảm thấy vui nhất hoặc tự hào nhất về ca làm việc của mình?",
            "",
            "🌱 'Cảm ơn sự tận tụy và chú tâm của tất cả các bạn trong tuần qua.'"
        ]
    }
    lines = prompts.get(weekday, prompts[0])
    return chr(10).join(lines)

def send_daily_hr_pulse(branch="Ming Coffee"):
    msg = get_daily_hr_pulse_message(branch)
    print(json.dumps({
        "status": "success",
        "branch": branch,
        "message": msg
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
        print("  check_shift_compliance <branch> [shift_type]")
        print("  escalate_shift <branch> <shift_type> <level> [reason]")
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
    elif cmd == "check_shift_compliance":
        if len(sys.argv) < 3:
            print("Error: check_shift_compliance requires <branch> [shift_type]")
            sys.exit(1)
        stype = sys.argv[3] if len(sys.argv) > 3 else "open"
        check_shift_compliance(sys.argv[2], stype)
    elif cmd == "escalate_shift":
        if len(sys.argv) < 5:
            print("Error: escalate_shift requires <branch> <shift_type> <level> [reason]")
            sys.exit(1)
        reason = sys.argv[5] if len(sys.argv) > 5 else ""
        escalate_shift(sys.argv[2], sys.argv[3], sys.argv[4], reason)
    elif cmd == "search_employee":
        if len(sys.argv) < 3:
            print("Error: search_employee requires <query>")
            sys.exit(1)
        search_employee(sys.argv[2])

    elif cmd == "log_hr_pulse":
        if len(sys.argv) < 7:
            print("Error: log_hr_pulse requires <branch> <employee> <pillar> <sentiment> <content> [is_confidential]")
            sys.exit(1)
        conf = sys.argv[7].lower() in ['true', '1', 'yes'] if len(sys.argv) > 7 else False
        log_hr_pulse(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], conf)
    elif cmd == "flag_hr_alert":
        if len(sys.argv) < 6:
            print("Error: flag_hr_alert requires <branch> <employee> <reason> <details>")
            sys.exit(1)
        flag_hr_alert(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    elif cmd == "send_monthly_survey":
        br = sys.argv[2] if len(sys.argv) > 2 else "all"
        send_monthly_survey(br)

    elif cmd == "create_delegated_task":
        create_delegated_task(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], sys.argv[7])
    elif cmd == "update_task_deadline":
        update_task_deadline(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "daily_task_report":
        daily_task_report()
    elif cmd == "record_uniform_check":
        notes = sys.argv[7] if len(sys.argv) > 7 else ""
        viol = sys.argv[6] if len(sys.argv) > 6 else ""
        record_uniform_check(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], viol, notes)
    elif cmd == "uniform_monthly_report":
        m = sys.argv[2] if len(sys.argv) > 2 else None
        uniform_monthly_report(m)
    elif cmd == "register_branch_manager":
        if len(sys.argv) < 4:
            print("Error: register_branch_manager requires <branch> <name> [role] [zalo_name] [zalo_uid]")
            sys.exit(1)
        r = sys.argv[4] if len(sys.argv) > 4 else "Quản lý"
        zn = sys.argv[5] if len(sys.argv) > 5 else ""
        zu = sys.argv[6] if len(sys.argv) > 6 else ""
        register_branch_manager(sys.argv[2], sys.argv[3], r, zn, zu)
    elif cmd == "get_branch_managers":
        get_branch_managers()
    elif cmd == "get_branch_roster":
        if len(sys.argv) < 3:
            print("Error: get_branch_roster requires <branch>")
            sys.exit(1)
        get_branch_roster(sys.argv[2])
    elif cmd == "check_in":
        if len(sys.argv) < 3:
            print("Error: check_in requires <employee> [time]")
            sys.exit(1)
        t = sys.argv[3] if len(sys.argv) > 3 else None
        attendance_check_in(sys.argv[2], t)
    elif cmd == "check_out":
        if len(sys.argv) < 3:
            print("Error: check_out requires <employee> [time]")
            sys.exit(1)
        t = sys.argv[3] if len(sys.argv) > 3 else None
        attendance_check_out(sys.argv[2], t)

    elif cmd == "send_daily_hr_pulse":
        br = sys.argv[2] if len(sys.argv) > 2 else "Ming Coffee"
        send_daily_hr_pulse(br)

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
