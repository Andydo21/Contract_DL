import requests
import json

url = "https://1f45-35-237-102-57.ngrok-free.app/api/v1/extract_clauses"
text = """CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc
---
HỢP ĐỒNG DỊCH VỤ TỔ CHỨC SỰ KIỆN HỘI NGHỊ

Hôm nay, ngày 18 tháng 07 năm 2026, tại Hà Nội:
Bên A: Công ty Cổ phần FPT Software (FPT Software JSC)
Bên B: Công ty Cổ phần Khách sạn Hồng Ngọc (Hong Ngoc Hotel)

Điều 1: Dịch vụ cung cấp
Bên B chịu trách nhiệm cung cấp hội trường lớn sức chứa 500 khách, dịch vụ tiệc buffet trưa và các thiết bị âm thanh ánh sáng phục vụ hội nghị FPT Techday 2026 vào ngày 15 tháng 10 năm 2026.

Điều 2: Phí dịch vụ
Tổng giá trị dịch vụ trọn gói tạm tính là 40,000 USD (đã bao gồm các phí dịch vụ phòng hội nghị và ăn uống).

Điều 3: Hủy bỏ dịch vụ và Phạt hủy phòng (Cancellation Fees)
Bên A có quyền hủy bỏ hợp đồng bằng văn bản gửi cho Bên B. Nếu Bên A hủy hợp đồng trước ngày diễn ra sự kiện từ 30 đến 60 ngày, Bên A phải trả khoản phí hủy tương đương 50% tổng giá trị dịch vụ. Nếu hủy hợp đồng trong vòng 30 ngày trước sự kiện, Bên A phải bồi thường 100% tổng giá trị dịch vụ và không được hoàn lại tiền đặt cọc."""

payload = {"text": text}
print(f"Sending POST to {url}...")
try:
    resp = requests.post(url, json=payload, timeout=60)
    print(f"Status: {resp.status_code}")
    print("Response JSON:")
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
except Exception as e:
    print(f"Error: {e}")
