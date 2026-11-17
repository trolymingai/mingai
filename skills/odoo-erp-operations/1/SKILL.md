---
name: odoo-erp-operations
description: Direct Odoo ERP 19 Operations via High-Speed Python CLI for Ming Coffee. Use when creating tasks, closing checklists, anti-fraud verifications, querying branch status, and onboarding staff into Odoo ERP.
---

# Odoo ERP Operations Skill (Ming Coffee System)

Ming AI manages all Odoo ERP 19 interactions using the high-speed local CLI: `odoo_cli` (hoặc `python3 odoo_cli.py`).
**CRITICAL SECURITY RULE:** Do NOT use `curl -X POST` or `curl -d` (they are blocked by safety policy). ALWAYS run `odoo_cli <command>` using the `exec` tool.

---

## 1. Đồng Bộ Hoàn Tất Checklist Ca Của Nhân Viên
Mỗi khi nhân sự báo cáo hoàn tất việc ca làm qua Zalo (chat nhóm hoặc chat 1-1):
```bash
odoo_cli sync_checklist "<Chi nhánh>" "<Tiêu đề công việc>" "<Tên hoặc SĐT nhân sự>" "done" "<Ghi chú / Số liệu đo thực tế>"
```
*Tự động tìm kiếm task hoặc tạo mới, gán người phụ trách, gắn nhãn xanh [Đạt chuẩn], chuyển stage Hoàn tất và ghi số liệu vào Chatter Odoo.*

---

## 2. Cơ Chế Chống Gian Lận & Cắm Cờ Bất Thường (Anti-Fraud Flagging)
Khi phát hiện nhân viên trả lời bừa, số liệu sai chuẩn F&B, báo vội (speed-run), hoặc nghi vấn gian lận:
```bash
odoo_cli flag_anomaly "<Chi nhánh hoặc Task ID>" "<Tiêu đề việc>" "<Tên nhân sự>" "<Lý do cảnh báo>" "[Số liệu nghi vấn]"
```
*Lập tức chuyển State sang '02_changes_requested' (Cần đối soát), cắm sao đỏ ưu tiên (Priority 1), gắn tag đỏ 'Nghi vấn báo ảo' và gửi cảnh báo đỏ lên Chatter cho Cửa hàng trưởng/CEO.*

---

## 3. Xác Thực Số Liệu Chuẩn F&B (Golden Standards Verification)
Kiểm tra xem số liệu nhân viên gửi có nằm trong dải an toàn của Ming Coffee hay không:
```bash
odoo_cli verify_metrics "<loại thông số>" "<giá trị>"
```
*Các loại thông số hỗ trợ:*
- `tu_mat`: 2.0 ~ 5.0 °C (Tủ mát quầy bar / tủ sữa)
- `tu_dong`: -18.0 ~ -14.0 °C (Tủ đông đá / nguyên liệu)
- `noi_hoi`: 1.1 ~ 1.3 bar (Áp suất boiler máy pha)
- `chiet_xuat`: 8.5 ~ 9.5 bar (Áp suất pump chiết xuất)
- `shot_time`: 25.0 ~ 30.0 giây (Thời gian chiết xuất espresso)
- `shot_out`: 35.0 ~ 38.0 g (Trọng lượng nước cốt espresso từ 18g bột)

---

## 4. Onboarding Nhân Sự & Tự Động Tạo Tài Khoản
Khi nhân sự mới cung cấp thông tin:
```bash
odoo_cli onboard_employee "<Họ tên>" "<Số điện thoại>" "<Email>" "<Chi nhánh>" "<Lịch làm / Ca>"
```

---

## 5. Tra Cứu Task & Danh Sách
- Tra cứu công việc của 1 nhân viên cụ thể:
  `odoo_cli get_staff_tasks "<Tên hoặc SĐT nhân viên>"`
- Tra cứu toàn bộ việc của chi nhánh:
  `odoo_cli get_tasks "<Chi nhánh>"`
- Danh sách chi nhánh:
  `odoo_cli list_branches`

---

## 7. Kiểm Soát Tuân Thủ Vòng Lặp Kín & Ma Trận Leo Thang (Closed-Loop SLA)
- Kiểm tra trạng thái hoàn thành checklist ca hôm nay:
  `odoo_cli check_shift_compliance "<Chi nhánh>" "<open / close>"`
- Kích hoạt ma trận leo thang khi quá hạn:
  `odoo_cli escalate_shift "<Chi nhánh>" "<open / close>" "<level: 1|2|3>" "<Lý do trễ hạn>"`
