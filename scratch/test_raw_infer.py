import requests
import json

url = "https://1f45-35-237-102-57.ngrok-free.app/api/v1/extract_entities"
text = """Bên B chịu trách nhiệm cung cấp hội trường lớn sức chứa 500 khách, dịch vụ tiệc buffet trưa và các thiết bị âm thanh ánh sáng phục vụ hội nghị FPT Techday 2026 vào ngày 15 tháng 10 năm 2026."""

payload = {"text": text}
print("Sending extraction request...")
resp = requests.post(url, json=payload)
print(f"Status: {resp.status_code}")
print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
