import requests
import json

url = "https://1f45-35-237-102-57.ngrok-free.app/api/v1/extract_entities"
text = """CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc
---
HỢP ĐỒNG DỊCH VỤ TỔ CHỨC SỰ KIỆN HỘI NGHỊ

Hôm nay, ngày 18 tháng 07 năm 2026, tại Hà Nội:
Bên A: Công ty Cổ phần FPT Software (FPT Software JSC)
Bên B: Công ty Cổ phần Khách sạn Hồng Ngọc (Hong Ngoc Hotel)"""

payload = {"text": text}
print("Sending extraction request for Preamble...")
try:
    resp = requests.post(url, json=payload)
    print(f"Status: {resp.status_code}")
    print("Response JSON:")
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
except Exception as e:
    print(f"Error: {e}")
