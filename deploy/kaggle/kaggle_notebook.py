import os
import nest_asyncio
import uvicorn
from pyngrok import ngrok
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
import json
import re

# 1. Cấu hình Ngrok
NGROK_AUTH_TOKEN = "2z2Jys005c289EvZifDWi1ViBBr_7nZ6ASrHHT7qpoJ3DgmQU" # Thay token của bạn vào đây
ngrok.set_auth_token(NGROK_AUTH_TOKEN)

# 2. Khởi tạo FastAPI
app = FastAPI(title="Kaggle AI Service")

# 3. Load Model từ HuggingFace
MODEL_ID = "phamthanhfd/contract-analysis-qwen2.5-3b"

print(f"Loading tokenizer {MODEL_ID}...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

print(f"Loading model {MODEL_ID} in 4-bit...")
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16,
)

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    quantization_config=bnb_config,
    device_map="auto"
)
model.eval()
print("Model loaded successfully!")

# 4. Pydantic Models
class ClauseInput(BaseModel):
    title: str
    content: str

class SummarizeRequest(BaseModel):
    clauses: List[ClauseInput]
    contract_metadata: dict = {}

class SummarizeResponse(BaseModel):
    summary: str

class EntityExtractRequest(BaseModel):
    text: str

class EntityExtractResponse(BaseModel):
    entities: dict

# 5. Core Inference Function
def infer(messages: list) -> str:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    inputs = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
    )
    input_ids = inputs["input_ids"].to(device)
    attention_mask = inputs.get("attention_mask")
    if attention_mask is not None:
        attention_mask = attention_mask.to(device)

    with torch.no_grad():
        outputs = model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=512,
            temperature=0.1,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )

    generated_ids = outputs[0][input_ids.shape[1]:]
    return tokenizer.decode(generated_ids, skip_special_tokens=True)

def clean_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    try:
        return json.loads(text)
    except:
        return {}

# 6. Endpoints
@app.post("/api/v1/summarize", response_model=SummarizeResponse)
async def summarize_contract(payload: SummarizeRequest):
    if not payload.clauses:
        raise HTTPException(status_code=400, detail="No clauses provided.")

    all_clauses_text = "\n\n".join(
        f"[{c.title}]\n{c.content[:800]}" for c in payload.clauses[:15] # Lấy 15 điều khoản đầu cho đỡ tràn context
    )

    prompt = [
        {
            "role": "system",
            "content": (
                "Bạn là chuyên gia pháp lý. Hãy viết TÓM TẮT ĐIỀU HÀNH (Executive Summary) "
                "cho hợp đồng dưới đây, bao gồm: Mục đích ký kết, Thông tin các bên, Giá trị hợp đồng, "
                "Thời hạn, Nghĩa vụ chính, Rủi ro trọng yếu. "
                "Viết bằng tiếng Việt, cô đọng trong đoạn văn 150-250 từ."
            ),
        },
        {"role": "user", "content": f"NỘI DUNG HỢP ĐỒNG:\n{all_clauses_text}"},
    ]

    try:
        summary_text = infer(prompt)
        return SummarizeResponse(summary=summary_text.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/extract_entities", response_model=EntityExtractResponse)
async def extract_entities(payload: EntityExtractRequest):
    prompt = [
        {
            "role": "system",
            "content": (
                "Bạn là hệ thống trích xuất thông tin hợp đồng tự động. "
                "Đọc đoạn văn bản và trích xuất các thông tin sau thành JSON: "
                "COMPANY_NAME (Tên công ty), TAX_CODE (Mã số thuế), CONTRACT_VALUE (Giá trị hợp đồng), "
                "DATE_EFFECTIVE (Ngày hiệu lực), DATE_EXPIRE (Ngày hết hạn). "
                "Chỉ trả về JSON hợp lệ, không giải thích gì thêm."
            )
        },
        {"role": "user", "content": payload.text}
    ]
    try:
        response_text = infer(prompt)
        entities = clean_json(response_text)
        return EntityExtractResponse(entities=entities)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy", "model": MODEL_ID}

# 7. Expose via Ngrok & Run Server
if __name__ == "__main__":
    public_url = ngrok.connect(8001).public_url
    print(f"==================================================")
    print(f"✅ NG_ROK PUBLIC URL: {public_url}")
    print(f"👉 Copy URL này và dán vào file .env của Django:")
    print(f"KAGGLE_AI_URL={public_url}")
    print(f"==================================================")
    import asyncio
    config = uvicorn.Config(app, host="0.0.0.0", port=8001)
    server = uvicorn.Server(config)
    await server.serve()

