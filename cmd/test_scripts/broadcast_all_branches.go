package main

import (
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/gorilla/websocket"
)

type Frame struct {
	Type   string         `json:"type"`
	ID     string         `json:"id,omitempty"`
	Method string         `json:"method,omitempty"`
	Params map[string]any `json:"params,omitempty"`
	Result any            `json:"result,omitempty"`
	Error  any            `json:"error,omitempty"`
}

func main() {
	header := http.Header{}
	c, _, err := websocket.DefaultDialer.Dial("ws://127.0.0.1:18790/ws", header)
	if err != nil {
		log.Fatalf("dial: %v", err)
	}
	defer c.Close()

	// 1. Connect
	connectReq := Frame{
		Type:   "req",
		ID:     "c1",
		Method: "connect",
		Params: map[string]any{
			"token":   "eae9134b7b6014847a75303456605872",
			"user_id": "system",
		},
	}
	c.WriteJSON(connectReq)
	var connectResp Frame
	c.ReadJSON(&connectResp)
	fmt.Printf("Connect: %+v\n\n", connectResp)

	dmNotice := `Chào bạn Cửa hàng trưởng,

📢 [CHỈ ĐẠO TỪ ANH MINH CEO - ĐỒNG BỘ DANH BẠ NHÂN SỰ TOÀN HỆ THỐNG]
Anh Minh CEO yêu cầu các CHT thông báo và trực tiếp đôn đốc 100% nhân sự tại cửa hàng tag @Troly Ming để giới thiệu bản thân theo cú pháp chuẩn:

👉 "Hi @Troly Ming , Mình là..., mình làm việc ở cửa hàng ....., ở vị trí......"

⏰ Thời hạn: Hoàn tất trước CUỐI NGÀY HÔM NAY.
⚠️ Lưu ý: Cuối ngày hôm nay, hệ thống Ming AI sẽ tự động quét danh bạ nhân sự trên Odoo ERP. Cửa hàng/nhân sự nào chưa hoàn tất, hệ thống sẽ tự động cập nhật báo cáo lên hệ thống quản trị ERP gửi Ban Điều Hành.

Nhờ bạn đôn đốc các bạn trong ca hoàn tất sớm nhé! Cảm ơn bạn.`

	dms := []struct {
		name string
		to   string
	}{
		{"Hồng Hoàng (Vận hành / Test CHT)", "131714954850459646"},
		{"Ngô Ngọc (CHT GOO A2)", "5945359089887665583"},
		{"Ngọc Thuỷ (CHT GOO Lê Duẩn)", "7929867505413189409"},
		{"Quangg (CHT MING A3)", "8323650366933171630"},
		{"Trúc Thanh (CHT Ming PR)", "3244794313129568042"},
		{"Thanh Quân (GOO Phước Thể)", "3666295940077903564"},
		{"Phùng Văn Luyện (Xưởng Rang / Sản Xuất)", "4218136593749622436"},
	}

	groups := []struct {
		name string
		to   string
		msg  string
	}{
		{
			name: "Goo-A2 | Tổng",
			to:   "5944076628365845072",
			msg: `📢 [THÔNG BÁO TỪ ANH MINH CEO - ĐỒNG BỘ DANH BẠ NHÂN SỰ]

Kính gửi CHT và toàn thể nhân sự chi nhánh GOO A2!

Anh Minh CEO yêu cầu toàn thể nhân sự cửa hàng tag @Troly Ming để giới thiệu bản thân và vị trí làm việc theo cú pháp chuẩn:

👉 "Hi @Troly Ming , Mình là..., mình làm việc ở cửa hàng ....., ở vị trí......"

⏰ Thời hạn: Hoàn tất trước CUỐI NGÀY HÔM NAY.
⚠️ Lưu ý: Cuối ngày hôm nay, hệ thống Ming AI sẽ tự động rà soát danh sách nhân sự trên Odoo ERP. Trường hợp nào chưa hoàn tất, hệ thống sẽ tự động cập nhật báo cáo trực tiếp lên hệ thống quản trị ERP gửi Ban Điều Hành.

Nhờ @all và CHT @Ngô Ngọc đôn đốc mọi người hoàn tất đúng hạn nhé!`,
		},
		{
			name: "Goo-Lê Duẩn | Tổng",
			to:   "2170546658158087218",
			msg: `📢 [THÔNG BÁO TỪ ANH MINH CEO - ĐỒNG BỘ DANH BẠ NHÂN SỰ]

Kính gửi CHT và toàn thể nhân sự chi nhánh GOO Lê Duẩn!

Anh Minh CEO yêu cầu toàn thể nhân sự cửa hàng tag @Troly Ming để giới thiệu bản thân và vị trí làm việc theo cú pháp chuẩn:

👉 "Hi @Troly Ming , Mình là..., mình làm việc ở cửa hàng ....., ở vị trí......"

⏰ Thời hạn: Hoàn tất trước CUỐI NGÀY HÔM NAY.
⚠️ Lưu ý: Cuối ngày hôm nay, hệ thống Ming AI sẽ tự động rà soát danh sách nhân sự trên Odoo ERP. Trường hợp nào chưa hoàn tất, hệ thống sẽ tự động cập nhật báo cáo trực tiếp lên hệ thống quản trị ERP gửi Ban Điều Hành.

Nhờ @all và CHT @Ngọc Thuỷ đôn đốc mọi người hoàn tất đúng hạn nhé!`,
		},
		{
			name: "MING A3 | Tổng",
			to:   "5435289813534943299",
			msg: `📢 [THÔNG BÁO TỪ ANH MINH CEO - ĐỒNG BỘ DANH BẠ NHÂN SỰ]

Kính gửi CHT và toàn thể nhân sự chi nhánh MING A3!

Anh Minh CEO yêu cầu toàn thể nhân sự cửa hàng tag @Troly Ming để giới thiệu bản thân và vị trí làm việc theo cú pháp chuẩn:

👉 "Hi @Troly Ming , Mình là..., mình làm việc ở cửa hàng ....., ở vị trí......"

⏰ Thời hạn: Hoàn tất trước CUỐI NGÀY HÔM NAY.
⚠️ Lưu ý: Cuối ngày hôm nay, hệ thống Ming AI sẽ tự động rà soát danh sách nhân sự trên Odoo ERP. Trường hợp nào chưa hoàn tất, hệ thống sẽ tự động cập nhật báo cáo trực tiếp lên hệ thống quản trị ERP gửi Ban Điều Hành.

Nhờ @all và CHT @Quangg đôn đốc mọi người hoàn tất đúng hạn nhé!`,
		},
		{
			name: "MING A3 | PC",
			to:   "7325150732309676165",
			msg: `📢 [THÔNG BÁO TỪ ANH MINH CEO - ĐỒNG BỘ DANH BẠ NHÂN SỰ]

Kính gửi CHT và team Pha chế MING A3!

Anh Minh CEO yêu cầu toàn thể nhân sự ca pha chế tag @Troly Ming để giới thiệu bản thân và vị trí làm việc theo cú pháp chuẩn:

👉 "Hi @Troly Ming , Mình là..., mình làm việc ở cửa hàng ....., ở vị trí......"

⏰ Thời hạn: Hoàn tất trước CUỐI NGÀY HÔM NAY.
⚠️ Lưu ý: Cuối ngày hôm nay, hệ thống Ming AI sẽ tự động rà soát danh sách nhân sự trên Odoo ERP. Trường hợp nào chưa hoàn tất, hệ thống sẽ tự động cập nhật báo cáo trực tiếp lên hệ thống quản trị ERP gửi Ban Điều Hành.

Nhờ @all và CHT @Quangg đôn đốc mọi người hoàn tất đúng hạn nhé!`,
		},
		{
			name: "Ming PR | Tổng",
			to:   "6099730162709364619",
			msg: `📢 [THÔNG BÁO TỪ ANH MINH CEO - ĐỒNG BỘ DANH BẠ NHÂN SỰ]

Kính gửi CHT và toàn thể nhân sự chi nhánh Ming Phan Rí!

Anh Minh CEO yêu cầu toàn thể nhân sự cửa hàng tag @Troly Ming để giới thiệu bản thân và vị trí làm việc theo cú pháp chuẩn:

👉 "Hi @Troly Ming , Mình là..., mình làm việc ở cửa hàng ....., ở vị trí......"

⏰ Thời hạn: Hoàn tất trước CUỐI NGÀY HÔM NAY.
⚠️ Lưu ý: Cuối ngày hôm nay, hệ thống Ming AI sẽ tự động rà soát danh sách nhân sự trên Odoo ERP. Trường hợp nào chưa hoàn tất, hệ thống sẽ tự động cập nhật báo cáo trực tiếp lên hệ thống quản trị ERP gửi Ban Điều Hành.

Nhờ @all và CHT @Trúc Thanh đôn đốc mọi người hoàn tất đúng hạn nhé!`,
		},
		{
			name: "Goo Phước Thể | Tổng",
			to:   "8145378988362298919",
			msg: `📢 [THÔNG BÁO TỪ ANH MINH CEO - ĐỒNG BỘ DANH BẠ NHÂN SỰ]

Kính gửi CHT và toàn thể nhân sự chi nhánh GOO Phước Thể!

Anh Minh CEO yêu cầu toàn thể nhân sự cửa hàng tag @Troly Ming để giới thiệu bản thân và vị trí làm việc theo cú pháp chuẩn:

👉 "Hi @Troly Ming , Mình là..., mình làm việc ở cửa hàng ....., ở vị trí......"

⏰ Thời hạn: Hoàn tất trước CUỐI NGÀY HÔM NAY.
⚠️ Lưu ý: Cuối ngày hôm nay, hệ thống Ming AI sẽ tự động rà soát danh sách nhân sự trên Odoo ERP. Trường hợp nào chưa hoàn tất, hệ thống sẽ tự động cập nhật báo cáo trực tiếp lên hệ thống quản trị ERP gửi Ban Điều Hành.

Nhờ @all , @Hồng Hoàng và @Thanh Quân đôn đốc mọi người hoàn tất đúng hạn nhé!`,
		},
		{
			name: "MING-Nơi chốn thứ 2",
			to:   "6214157677241296400",
			msg: `📢 [THÔNG BÁO TỪ ANH MINH CEO - ĐỒNG BỘ DANH BẠ NHÂN SỰ]

Kính gửi toàn thể nhân sự MING - Nơi Chốn Thứ 2!

Anh Minh CEO yêu cầu toàn thể nhân sự tag @Troly Ming để giới thiệu bản thân và vị trí làm việc theo cú pháp chuẩn:

👉 "Hi @Troly Ming , Mình là..., mình làm việc ở cửa hàng ....., ở vị trí......"

⏰ Thời hạn: Hoàn tất trước CUỐI NGÀY HÔM NAY.
⚠️ Lưu ý: Cuối ngày hôm nay, hệ thống Ming AI sẽ tự động rà soát danh sách nhân sự trên Odoo ERP. Trường hợp nào chưa hoàn tất, hệ thống sẽ tự động cập nhật báo cáo trực tiếp lên hệ thống quản trị ERP gửi Ban Điều Hành.

Nhờ @all và @Hồng Hoàng đôn đốc mọi người hoàn tất đúng hạn nhé!`,
		},
		{
			name: "MING|Bán hàng",
			to:   "1865171399962457807",
			msg: `📢 [THÔNG BÁO TỪ ANH MINH CEO - ĐỒNG BỘ DANH BẠ NHÂN SỰ]

Kính gửi toàn thể nhân sự Khối Bán Hàng & Cửa Hàng!

Anh Minh CEO yêu cầu toàn thể nhân sự tag @Troly Ming để giới thiệu bản thân và vị trí làm việc theo cú pháp chuẩn:

👉 "Hi @Troly Ming , Mình là..., mình làm việc ở cửa hàng ....., ở vị trí......"

⏰ Thời hạn: Hoàn tất trước CUỐI NGÀY HÔM NAY.
⚠️ Lưu ý: Cuối ngày hôm nay, hệ thống Ming AI sẽ tự động rà soát danh sách nhân sự trên Odoo ERP. Trường hợp nào chưa hoàn tất, hệ thống sẽ tự động cập nhật báo cáo trực tiếp lên hệ thống quản trị ERP gửi Ban Điều Hành.

Nhờ @all và các bạn CHT @Ngô Ngọc , @Ngọc Thuỷ , @Quangg , @Trúc Thanh đôn đốc team hoàn tất đúng hạn!`,
		},
		{
			name: "MING|Quản lý",
			to:   "3848125694699364170",
			msg: `📢 [CHỈ ĐẠO TỪ ANH MINH CEO - ĐỒNG BỘ DANH BẠ NHÂN SỰ TOÀN HỆ THỐNG]

Kính gửi Ban Quản Lý và các bạn Cửa Hàng Trưởng!

Anh Minh CEO yêu cầu các CHT thông báo và trực tiếp đôn đốc 100% nhân sự chi nhánh tag @Troly Ming để giới thiệu bản thân theo cú pháp chuẩn:

👉 "Hi @Troly Ming , Mình là..., mình làm việc ở cửa hàng ....., ở vị trí......"

⏰ Thời hạn: Hoàn tất trước CUỐI NGÀY HÔM NAY.
⚠️ Cuối ngày hôm nay hệ thống Ming AI sẽ tự động rà soát danh sách nhân sự trên Odoo ERP để lập báo cáo Ban Điều Hành.

Nhờ @all , @Hồng Hoàng , @Ngô Ngọc , @Ngọc Thuỷ , @Quangg , @Trúc Thanh đôn đốc toàn bộ nhân sự các ca hoàn tất nghiêm túc!`,
		},
		{
			name: "MING|CUNG ỨNG|CỬA HÀNG",
			to:   "285073119289277145",
			msg: `📢 [THÔNG BÁO TỪ ANH MINH CEO - ĐỒNG BỘ DANH BẠ NHÂN SỰ]

Kính gửi toàn thể nhân sự Bộ phận Cung Ứng & Cửa Hàng!

Anh Minh CEO yêu cầu toàn thể nhân sự tag @Troly Ming để giới thiệu bản thân và vị trí làm việc theo cú pháp chuẩn:

👉 "Hi @Troly Ming , Mình là..., mình làm việc ở cửa hàng ....., ở vị trí......"

⏰ Thời hạn: Hoàn tất trước CUỐI NGÀY HÔM NAY.
⚠️ Cuối ngày hôm nay hệ thống sẽ quét Odoo ERP để cập nhật báo cáo quản trị.

Nhờ @all , @Hồng Hoàng và @Phùng Văn Luyện đôn đốc các bạn hoàn tất sớm nhé!`,
		},
		{
			name: "Ming|Báo sự cố",
			to:   "2785144727994011019",
			msg: `📢 [THÔNG BÁO TỪ ANH MINH CEO - ĐỒNG BỘ DANH BẠ NHÂN SỰ]

Kính gửi toàn thể nhân sự và kỹ thuật các chi nhánh!

Anh Minh CEO yêu cầu toàn thể nhân sự tag @Troly Ming để giới thiệu bản thân và vị trí làm việc theo cú pháp chuẩn:

👉 "Hi @Troly Ming , Mình là..., mình làm việc ở cửa hàng ....., ở vị trí......"

⏰ Thời hạn: Hoàn tất trước CUỐI NGÀY HÔM NAY.
⚠️ Cuối ngày hôm nay hệ thống Ming AI sẽ tự động quét danh bạ nhân sự trên Odoo ERP để báo cáo Ban Điều Hành.

Nhờ @all và @Hồng Hoàng đôn đốc mọi người hoàn tất đúng hạn nhé!`,
		},
		{
			name: "Test Ming AI",
			to:   "552328793123364999",
			msg: `📢 [THÔNG BÁO TỪ ANH MINH CEO - ĐỒNG BỘ DANH BẠ NHÂN SỰ]

Kính gửi CHT và toàn thể nhân sự!

Anh Minh CEO yêu cầu toàn thể nhân sự tag @Troly Ming để giới thiệu bản thân và vị trí làm việc theo cú pháp chuẩn:

👉 "Hi @Troly Ming , Mình là..., mình làm việc ở cửa hàng ....., ở vị trí......"

⏰ Thời hạn: Hoàn tất trước CUỐI NGÀY HÔM NAY.
⚠️ Lưu ý: Cuối ngày hôm nay, hệ thống Ming AI sẽ tự động rà soát danh sách nhân sự trên Odoo ERP. Trường hợp nào chưa hoàn tất, hệ thống sẽ tự động cập nhật báo cáo trực tiếp lên hệ thống quản trị ERP gửi Ban Điều Hành.

Nhờ @all và @Hồng Hoàng đôn đốc mọi người hoàn tất đúng hạn nhé!`,
		},
	}

	fmt.Println("=== 1. GỬI TIN NHẮN RIÊNG CHO CÁC CỬA HÀNG TRƯỞNG & QUẢN LÝ ===")
	for i, d := range dms {
		req := Frame{
			Type:   "req",
			ID:     fmt.Sprintf("dm_%d", i),
			Method: "send",
			Params: map[string]any{
				"channel": "zalo-ming-ai",
				"to":      d.to,
				"message": dmNotice,
			},
		}
		c.WriteJSON(req)
		var resp Frame
		c.ReadJSON(&resp)
		fmt.Printf("DM to %s (%s): %+v\n", d.name, d.to, resp)
		time.Sleep(1 * time.Second)
	}

	fmt.Println("\n=== 2. GỬI VÀO TẤT CẢ CÁC NHÓM CHI NHÁNH & BỘ PHẬN CỬA HÀNG ===")
	for i, g := range groups {
		req := Frame{
			Type:   "req",
			ID:     fmt.Sprintf("grp_%d", i),
			Method: "send",
			Params: map[string]any{
				"channel": "zalo-ming-ai",
				"to":      g.to,
				"message": g.msg,
			},
		}
		c.WriteJSON(req)
		var resp Frame
		c.ReadJSON(&resp)
		fmt.Printf("Group [%s] (%s): %+v\n", g.name, g.to, resp)
		time.Sleep(1 * time.Second)
	}

	fmt.Println("\nĐang chờ 5s để đảm bảo toàn bộ message bus hoàn tất gửi...")
	time.Sleep(5 * time.Second)
	fmt.Println("=== HOÀN TẤT TOÀN BỘ PHÁT SÓNG ===")
}
