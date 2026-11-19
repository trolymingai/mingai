#!/usr/bin/env python3
import json
import os
import sys
import re
import time
import datetime
import uuid
import zipfile
import io
import csv
import psycopg2

try:
    import docx
except ImportError:
    docx = None

try:
    import pypdf
except ImportError:
    pypdf = None

try:
    import openpyxl
except ImportError:
    openpyxl = None

try:
    import requests
except ImportError:
    requests = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
AUDIT_LOG = os.path.join(BASE_DIR, "audit.log")
KB_BASE_DIR = "/app/workspace/company_kb"
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(KB_BASE_DIR, exist_ok=True)

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

# --- 1. PROMPT VIEW ---
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

# --- 2. PROMPT UPDATE ---
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

        ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"frontmatter_{ts_str}.md")
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(current_frontmatter)

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

        cur.execute("UPDATE agents SET frontmatter = %s, updated_at = NOW() WHERE agent_key = %s;", (new_frontmatter, AGENT_KEY))

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

# --- 3. PROMPT ROLLBACK ---
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

# --- 4. ROBUST FILE & GOOGLE DRIVE / DOCS PARSER ---
def tool_read_and_parse_file(args):
    target = (args.get("file_path_or_url") or "").strip()
    if not target:
        return {"ok": False, "error": "Vui lòng cung cấp file_path_or_url (đường dẫn tệp tin hoặc liên kết Drive/Docs)."}

    # Case A: Google Drive / Docs / Sheets URL or web link
    if target.startswith("http://") or target.startswith("https://"):
        if not requests:
            return {"ok": False, "error": "requests library is required for URL downloads"}

        session = requests.Session()
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

        m_doc = re.search(r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)", target)
        m_sheet = re.search(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)", target)
        m_slide = re.search(r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)", target)
        m_file = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", target)

        try:
            # A1: Google Docs
            if m_doc:
                doc_id = m_doc.group(1)
                export_url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
                resp = session.get(export_url, headers=headers, timeout=25, allow_redirects=True)
                if "accounts.google.com" in resp.url or "ServiceLogin" in resp.text:
                    return {
                        "ok": False,
                        "error": "Tài liệu Google Docs này đang ở chế độ RIÊNG TƯ. Vui lòng chọn 'Bất kỳ ai có liên kết đều có thể xem' (Anyone with link can view) để Ming AI đọc được."
                    }
                text = resp.text.strip()
                return {
                    "ok": True,
                    "doc_type": "google_doc",
                    "doc_id": doc_id,
                    "url": target,
                    "char_count": len(text),
                    "preview": text[:500],
                    "content": text
                }

            # A2: Google Sheets
            elif m_sheet:
                sheet_id = m_sheet.group(1)
                export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
                resp = session.get(export_url, headers=headers, timeout=25, allow_redirects=True)
                if "accounts.google.com" in resp.url or "ServiceLogin" in resp.text:
                    return {
                        "ok": False,
                        "error": "Bảng tính Google Sheets này đang ở chế độ RIÊNG TƯ. Vui lòng mở quyền công khai để Ming AI đọc dữ liệu."
                    }
                csv_text = resp.text.strip()
                # Format CSV rows nicely
                rows = []
                reader = csv.reader(io.StringIO(csv_text))
                for r in reader:
                    if any(r):
                        rows.append(" | ".join([cell.strip() for cell in r]))
                full_text = "\n".join(rows)
                return {
                    "ok": True,
                    "doc_type": "google_sheet",
                    "sheet_id": sheet_id,
                    "url": target,
                    "row_count": len(rows),
                    "char_count": len(full_text),
                    "preview": full_text[:500],
                    "content": full_text
                }

            # A3: Google Slides
            elif m_slide:
                slide_id = m_slide.group(1)
                export_url = f"https://docs.google.com/presentation/d/{slide_id}/export/txt"
                resp = session.get(export_url, headers=headers, timeout=25, allow_redirects=True)
                text = resp.text.strip()
                return {
                    "ok": True,
                    "doc_type": "google_slide",
                    "slide_id": slide_id,
                    "url": target,
                    "char_count": len(text),
                    "preview": text[:500],
                    "content": text
                }

            # A4: Google Drive file (PDF, Word, Excel, Text, etc.)
            elif m_file:
                file_id = m_file.group(1)
                dl_url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t"
                resp = session.get(dl_url, headers=headers, timeout=35, allow_redirects=True)

                if "accounts.google.com" in resp.url or "ServiceLogin" in resp.text:
                    return {
                        "ok": False,
                        "error": "Tệp tin Google Drive này đang ở chế độ RIÊNG TƯ. Vui lòng mở quyền 'Bất kỳ ai có liên kết đều có thể xem' để Ming AI đọc được."
                    }

                content = resp.content
                # Handle large file virus confirmation page
                if b"confirm=" in content and b"Google Drive" in content:
                    m_token = re.search(r"confirm=([0-9A-Za-z_-]+)", resp.text)
                    if m_token:
                        resp = session.get(f"{dl_url}&confirm={m_token.group(1)}", headers=headers, timeout=35, allow_redirects=True)
                        content = resp.content

                header = content[:16]
                extracted_text = ""
                doc_type = "google_drive_file"

                # Check PDF
                if header.startswith(b"%PDF-"):
                    doc_type = "pdf_on_drive"
                    if pypdf:
                        try:
                            reader = pypdf.PdfReader(io.BytesIO(content))
                            pages = [p.extract_text() or "" for p in reader.pages]
                            extracted_text = "\n\n".join(pages).strip()
                        except Exception as e:
                            return {"ok": False, "error": f"Lỗi đọc file PDF từ Google Drive: {str(e)}"}

                # Check ZIP / DOCX / XLSX
                elif header.startswith(b"PK\x03\x04"):
                    try:
                        with zipfile.ZipFile(io.BytesIO(content)) as z:
                            if "word/document.xml" in z.namelist():
                                doc_type = "docx_on_drive"
                                if docx:
                                    doc = docx.Document(io.BytesIO(content))
                                    paras = [p.text for p in doc.paragraphs if p.text.strip()]
                                    tables_text = []
                                    for table in doc.tables:
                                        for row in table.rows:
                                            row_cells = [cell.text.strip() for cell in row.cells]
                                            tables_text.append(" | ".join(row_cells))
                                    extracted_text = "\n".join(paras)
                                    if tables_text:
                                        extracted_text += "\n\n### BẢNG DỮ LIỆU ĐÍNH KÈM:\n" + "\n".join(tables_text)
                            elif "xl/workbook.xml" in z.namelist():
                                doc_type = "xlsx_on_drive"
                                if openpyxl:
                                    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
                                    sheets_text = []
                                    for sheet in wb.worksheets:
                                        sheets_text.append(f"### SHEET: {sheet.title}")
                                        for row in sheet.iter_rows(values_only=True):
                                            if any(row):
                                                clean_cells = [str(c).strip() if c is not None else "" for c in row]
                                                sheets_text.append(" | ".join(clean_cells))
                                    extracted_text = "\n".join(sheets_text).strip()
                    except Exception:
                        pass

                # Fallback text
                if not extracted_text:
                    try:
                        extracted_text = content.decode("utf-8", errors="replace").strip()
                    except Exception:
                        pass

                if not extracted_text:
                    return {"ok": False, "error": "Không trích xuất được nội dung chữ từ file Google Drive này."}

                return {
                    "ok": True,
                    "doc_type": doc_type,
                    "file_id": file_id,
                    "url": target,
                    "size_bytes": len(content),
                    "char_count": len(extracted_text),
                    "preview": extracted_text[:500],
                    "content": extracted_text
                }

            # Generic web URL
            else:
                resp = session.get(target, headers=headers, timeout=20)
                text = resp.text.strip()
                return {
                    "ok": True,
                    "doc_type": "web_url",
                    "url": target,
                    "char_count": len(text),
                    "preview": text[:500],
                    "content": text
                }
        except Exception as e:
            return {"ok": False, "error": f"Lỗi tải dữ liệu từ Google Drive/Web: {str(e)}"}

    # Case B: Local file path
    possible_paths = [
        target,
        os.path.join("/app/workspace", target),
        os.path.join("/app/workspace/.media", target),
        os.path.join("/app/workspace/company_kb", target),
        os.path.join("/tmp", target)
    ]
    file_path = None
    for p in possible_paths:
        if os.path.exists(p) and os.path.isfile(p):
            file_path = p
            break

    if not file_path:
        return {"ok": False, "error": f"Không tìm thấy tệp tin: '{target}'. Vui lòng kiểm tra lại đường dẫn."}

    file_size = os.path.getsize(file_path)
    if file_size == 0:
        return {"ok": False, "error": "Tệp tin rỗng (0 bytes)."}

    with open(file_path, "rb") as f:
        header = f.read(16)

    extracted_text = ""
    doc_type = "unknown"

    # PDF
    if header.startswith(b"%PDF-") or file_path.lower().endswith(".pdf"):
        doc_type = "pdf"
        if pypdf:
            try:
                reader = pypdf.PdfReader(file_path)
                pages = [page.extract_text() or "" for page in reader.pages]
                extracted_text = "\n\n".join(pages).strip()
            except Exception:
                pass

    # DOCX (Word)
    elif (header.startswith(b"PK\x03\x04") or file_path.lower().endswith(".docx")) and not file_path.lower().endswith(".xlsx"):
        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                if 'word/document.xml' in z.namelist():
                    doc_type = "docx"
                    if docx:
                        doc = docx.Document(file_path)
                        paras = [p.text for p in doc.paragraphs if p.text.strip()]
                        tables_text = []
                        for table in doc.tables:
                            for row in table.rows:
                                row_cells = [cell.text.strip() for cell in row.cells]
                                tables_text.append(" | ".join(row_cells))
                        extracted_text = "\n".join(paras)
                        if tables_text:
                            extracted_text += "\n\n### BẢNG DỮ LIỆU ĐÍNH KÈM:\n" + "\n".join(tables_text)
        except Exception:
            pass

    # XLSX (Excel)
    if not extracted_text and (file_path.lower().endswith(".xlsx") or file_path.lower().endswith(".xls")):
        doc_type = "xlsx"
        if openpyxl:
            try:
                wb = openpyxl.load_workbook(file_path, data_only=True)
                sheets_text = []
                for sheet in wb.worksheets:
                    sheets_text.append(f"### SHEET: {sheet.title}")
                    for row in sheet.iter_rows(values_only=True):
                        if any(row):
                            clean_cells = [str(c).strip() if c is not None else "" for c in row]
                            sheets_text.append(" | ".join(clean_cells))
                extracted_text = "\n".join(sheets_text).strip()
            except Exception:
                pass

    # Fallback to UTF-8 plain text
    if not extracted_text:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                extracted_text = f.read().strip()
                doc_type = "text"
        except Exception as e:
            return {"ok": False, "error": f"Không thể giải mã tệp tin: {str(e)}"}

    if not extracted_text:
        return {"ok": False, "error": "Không trích xuất được nội dung chữ từ tệp tin này."}

    return {
        "ok": True,
        "doc_type": doc_type,
        "file_name": os.path.basename(file_path),
        "file_path": file_path,
        "size_bytes": file_size,
        "char_count": len(extracted_text),
        "preview": extracted_text[:500],
        "content": extracted_text
    }

# --- 5. INGEST KNOWLEDGE BASE ---
def tool_ingest_kb(args):
    uid = args.get("requester_zalo_uid")
    name = args.get("requester_name")
    title = (args.get("title") or "").strip()
    category = (args.get("category") or "SOP").upper().strip()
    content = (args.get("content") or "").strip()
    tags = (args.get("tags") or "").strip()
    sync_to_context = args.get("sync_to_context_file", True)

    if not is_authorized(uid, name):
        return {
            "ok": False,
            "error": f"LỖI PHÂN QUYỀN (ACCESS DENIED): Chỉ duy nhất Anh Minh CEO (Zalo UID: {AUTHORIZED_CEO_UID}) mới có thẩm quyền nạp hoặc cập nhật Kho Tri Thức của Ming AI.",
            "authorized": False
        }

    if not title:
        return {"ok": False, "error": "Tiêu đề tài liệu (title) không được để trống."}
    if not content:
        return {"ok": False, "error": "Nội dung tài liệu (content) không được để trống."}

    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", title.lower())[:45]
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    # 5.1. Write to company_kb directory
    cat_dir = os.path.join(KB_BASE_DIR, category)
    os.makedirs(cat_dir, exist_ok=True)
    kb_file_path = os.path.join(cat_dir, f"{slug}.md")

    header = f"---\ntitle: {title}\ncategory: {category}\ntags: {tags}\ncreated: {date_str}\nauthor: CEO Dương Vương Minh\n---\n\n# {title}\n\n"
    with open(kb_file_path, "w", encoding="utf-8") as f:
        f.write(header + content + "\n")

    # 5.2. Update _index.md
    index_file = os.path.join(KB_BASE_DIR, "_index.md")
    index_line = f"- [{category}] **{title}**: `{category}/{slug}.md` (Thẻ: {tags}) - Cập nhật: {now_str}\n"
    if not os.path.exists(index_file):
        with open(index_file, "w", encoding="utf-8") as f:
            f.write("# MỤC LỤC KHO TRI THỨC MING COFFEE (COMPANY KB)\n\n" + index_line)
    else:
        with open(index_file, "a", encoding="utf-8") as f:
            f.write(index_line)

    # 5.3. Ingest into PostgreSQL vault_documents
    vault_id = str(uuid.uuid4())
    summary = content[:350].replace("\n", " ")
    try:
        conn = psycopg2.connect(DSN)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO vault_documents 
            (id, tenant_id, scope, path, title, doc_type, summary, created_at, updated_at)
            VALUES (%s, %s, 'shared', %s, %s, 'sop', %s, NOW(), NOW())
            ON CONFLICT (id) DO NOTHING;
        """, (vault_id, TENANT_ID, f"company_kb/{category}/{slug}.md", title, summary))

        # 5.4. Sync summary into KNOWLEDGE_BASE.md in agent_context_files
        if sync_to_context:
            cur.execute("SELECT content FROM agent_context_files WHERE agent_id = %s AND file_name = 'KNOWLEDGE_BASE.md';", (AGENT_ID,))
            kb_row = cur.fetchone()
            kb_entry = f"""
### [{category}] {title} (Cập nhật bởi CEO Dương Vương Minh ngày {now_str})
- **Đường dẫn tệp**: `company_kb/{category}/{slug}.md`
- **Từ khóa tra cứu**: {tags or title}
- **Tóm tắt nội dung**:
{summary}
"""
            if kb_row and kb_row[0]:
                updated_kb_content = kb_row[0] + "\n" + kb_entry
                cur.execute("UPDATE agent_context_files SET content = %s, updated_at = NOW() WHERE agent_id = %s AND file_name = 'KNOWLEDGE_BASE.md';", (updated_kb_content, AGENT_ID))
            else:
                cur.execute("""
                    INSERT INTO agent_context_files (id, agent_id, file_name, content, created_at, updated_at, tenant_id)
                    VALUES (gen_random_uuid(), %s, 'KNOWLEDGE_BASE.md', %s, NOW(), NOW(), %s);
                """, (AGENT_ID, f"# KHO TRI THỨC & QUY CHUẨN VẬN HÀNH MING COFFEE\n{kb_entry}", TENANT_ID))

        conn.commit()
        conn.close()
    except Exception as e:
        return {"ok": False, "error": f"Lỗi lưu trữ cơ sở dữ liệu: {str(e)}"}

    log_audit("INGEST_KB", {
        "uid": uid,
        "name": name,
        "title": title,
        "category": category,
        "file": kb_file_path,
        "vault_id": vault_id
    })

    return {
        "ok": True,
        "status": "INGESTED_TO_KNOWLEDGE_BASE",
        "title": title,
        "category": category,
        "tags": tags,
        "file_path": kb_file_path,
        "vault_id": vault_id,
        "message": f"Đã nạp vĩnh viễn tài liệu '{title}' vào Kho Tri Thức Chung (danh mục: {category}). Toàn bộ 10 nhóm Zalo và Ming AI đều có thể tra cứu và thực thi theo chuẩn này!"
    }

# --- 6. SEARCH KNOWLEDGE BASE ---
def tool_search_kb(args):
    query = (args.get("query") or "").strip().lower()
    index_file = os.path.join(KB_BASE_DIR, "_index.md")
    if not os.path.exists(index_file):
        return {"ok": True, "total": 0, "results": [], "message": "Kho tri thức hiện chưa có tài liệu nào."}

    hits = []
    for root, dirs, files in os.walk(KB_BASE_DIR):
        for file in files:
            if file.endswith(".md") and not file.startswith("_"):
                full_p = os.path.join(root, file)
                try:
                    with open(full_p, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                        if query in text.lower():
                            rel_p = os.path.relpath(full_p, KB_BASE_DIR)
                            m_title = re.search(r"title:\s*(.*)", text)
                            title = m_title.group(1).strip() if m_title else file
                            hits.append({
                                "title": title,
                                "path": rel_p,
                                "snippet": text[:400]
                            })
                except Exception:
                    pass

    return {
        "ok": True,
        "query": query,
        "total_hits": len(hits),
        "results": hits[:10]
    }

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
    },
    "ceo_read_and_parse_file": {
        "description": "Đọc và bóc tách toàn bộ nội dung từ tệp tin bất kỳ (Word .docx, PDF, Excel .xlsx, CSV, TXT, JSON, MD, hoặc liên kết Google Drive, Google Docs, Google Sheets, Google Slides) cho TẤT CẢ CÁC THÀNH VIÊN TRONG CÔNG TY khi được yêu cầu.",
        "schema": {
            "type": "object",
            "properties": {
                "file_path_or_url": {"type": "string", "description": "Đường dẫn tệp tin trên hệ thống hoặc liên kết Google Drive/Docs/Sheets"},
                "requester_zalo_uid": {"type": "string", "description": "UID Zalo của người gửi yêu cầu"}
            },
            "required": ["file_path_or_url"]
        },
        "fn": tool_read_and_parse_file
    },
    "ceo_ingest_knowledge_base": {
        "description": "Nạp tài liệu, công thức, SOP, hoặc quy chuẩn mới vào Kho Tri Thức Chung (Company KB & Vault) của Ming AI theo chỉ đạo của Anh Minh CEO, cập nhật mục lục và phân quyền tra cứu toàn chuỗi. CHỈ DUY NHẤT ANH MINH CEO MỚI ĐƯỢC PHÉP THỰC HIỆN.",
        "schema": {
            "type": "object",
            "properties": {
                "requester_zalo_uid": {"type": "string", "description": "UID Zalo của người yêu cầu (bắt buộc: 3322195382887364919)"},
                "requester_name": {"type": "string", "description": "Tên người yêu cầu ('Vương Minh' / 'Anh Minh')"},
                "title": {"type": "string", "description": "Tiêu đề tài liệu hoặc quy chuẩn (ví dụ: 'Quy Chuẩn Pha Chế Trà Sữa Đậm Vị 2026')"},
                "category": {"type": "string", "enum": ["SOP_PHA_CHE", "SOP_BAN_HANG", "SOP_VAN_HANH", "QUY_DINH_NHAN_SU", "CSKH", "GENERAL"], "description": "Danh mục tri thức"},
                "content": {"type": "string", "description": "Toàn bộ nội dung chữ của tài liệu hoặc quy chuẩn"},
                "tags": {"type": "string", "description": "Từ khóa thẻ tìm kiếm, phân cách bằng dấu phẩy (ví dụ: 'tra_sua,cong_thuc,dinh_luong')"},
                "sync_to_context_file": {"type": "boolean", "default": True, "description": "Có đồng bộ trực tiếp vào KNOWLEDGE_BASE.md cho Ming AI hay không"}
            },
            "required": ["requester_zalo_uid", "title", "content"]
        },
        "fn": tool_ingest_kb
    },
    "ceo_search_knowledge_base": {
        "description": "Tra cứu nhanh các tài liệu, quy chuẩn, công thức trong Kho Tri Thức Chung (Company KB) của Ming AI theo từ khóa.",
        "schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Từ khóa cần tra cứu trong kho tri thức"}
            },
            "required": ["query"]
        },
        "fn": tool_search_kb
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
            return {"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "ceo-coach", "version": "2.1.0"}}}
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