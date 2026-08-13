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

prompts = [
    # 1. Standard prompt
    None, 
    # 2. Simple Vietnamese prompt
    "Trích xuất các thông tin hợp đồng sau thành JSON với các trường: COMPANY_NAME (danh sách tên công ty), TAX_CODE (mã số thuế), CONTRACT_VALUE (giá trị). Chỉ trả về JSON.",
    # 3. English prompt
    "Extract entities from this contract text into JSON with keys: COMPANY_NAME, TAX_CODE, CONTRACT_VALUE. Return ONLY JSON.",
    # 4. Prompt asking specifically for organizations
    "Đọc văn bản và trích xuất thông tin: Tên các bên ký kết hợp đồng (COMPANY_NAME). Trả về JSON."
]

for i, p in enumerate(prompts):
    print(f"\n--- PROMPT {i+1} ---")
    payload = {"text": text}
    if p:
        payload["system_prompt"] = p
    try:
        resp = requests.post(url, json=payload, timeout=60)
        result = resp.json()
        print(f"Status: {resp.status_code}")
        print("Raw response from LLM:")
        print(result.get("raw_response"))
        print("Parsed entities:")
        print(json.dumps(result.get("entities"), indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error: {e}")
