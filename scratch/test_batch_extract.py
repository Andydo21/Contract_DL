import requests
import json

url = "https://1f45-35-237-102-57.ngrok-free.app/api/v1/extract_entities_batch"
payload = {
    "clauses": [
        {
            "title": "Phần mở đầu",
            "content": "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nĐộc lập - Tự do - Hạnh phúc\n---\nHỢP ĐỒNG DỊCH VỤ TỔ CHỨC SỰ KIỆN HỘI NGHỊ\n\nHôm nay, ngày 18 tháng 07 năm 2026, tại Hà Nội:\nBên A: Công ty Cổ phần FPT Software (FPT Software JSC)\nBên B: Công ty Cổ phần Khách sạn Hồng Ngọc (Hong Ngoc Hotel)"
        },
        {
            "title": "Điều 1: Dịch vụ cung cấp",
            "content": "Bên B chịu trách nhiệm cung cấp hội trường lớn sức chứa 500 khách, dịch vụ tiệc buffet trưa và các thiết bị âm thanh ánh sáng phục vụ hội nghị FPT Techday 2026 vào ngày 15 tháng 10 năm 2026."
        },
        {
            "title": "Điều 2: Phí dịch vụ",
            "content": "Tổng giá trị dịch vụ trọn gói tạm tính là 40,000 USD (đã bao gồm các phí dịch vụ phòng hội nghị và ăn uống)."
        },
        {
            "title": "Điều 3: Hủy bỏ dịch vụ và Phạt hủy phòng (Cancellation Fees)",
            "content": "Bên A có quyền hủy bỏ hợp đồng bằng văn bản gửi cho Bên B. Nếu Bên A hủy hợp đồng trước ngày diễn ra sự kiện từ 30 đến 60 ngày, Bên A phải trả khoản phí hủy tương đương 50% tổng giá trị dịch vụ. Nếu hủy hợp đồng trong vòng 30 ngày trước sự kiện, Bên A phải bồi thường 100% tổng giá trị dịch vụ và không được hoàn lại tiền đặt cọc."
        }
    ]
}

try:
    resp = requests.post(url, json=payload, timeout=90)
    with open('d:\\Django_project\\RiskDL\\scratch\\batch_extract_results.txt', 'w', encoding='utf-8') as f:
        f.write(f"Status: {resp.status_code}\n")
        f.write(json.dumps(resp.json(), indent=2, ensure_ascii=False))
except Exception as e:
    with open('d:\\Django_project\\RiskDL\\scratch\\batch_extract_results.txt', 'w', encoding='utf-8') as f:
        f.write(f"Error: {e}\n")
print("Done writing results to batch_extract_results.txt")
