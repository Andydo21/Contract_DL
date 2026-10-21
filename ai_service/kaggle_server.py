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
app = FastAPI(title="Unified Kaggle AI Service")

# 3. Load Model từ HuggingFace
MODEL_ID = "Doan2108/contract-risk-qwen2.5-3b-merged"

print(f"Loading tokenizer {MODEL_ID}...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

print(f"Loading model {MODEL_ID}...")
# Cấu hình load float16 trực tiếp (phù hợp với GPU của Kaggle)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.float16,
    device_map="auto"
)

# Hoặc nếu muốn dùng 4-bit để tiết kiệm VRAM:
# bnb_config = BitsAndBytesConfig(
#     load_in_4bit=True,
#     bnb_4bit_use_double_quant=True,
#     bnb_4bit_quant_type="nf4",
#     bnb_4bit_compute_dtype=torch.float16,
# )
# model = AutoModelForCausalLM.from_pretrained(
#     MODEL_ID,
#     quantization_config=bnb_config,
#     device_map="auto"
# )

model.eval()
print("Model loaded successfully!")

# 4. Pydantic Models
class ClauseInput(BaseModel):
    title: str
    content: str

# --- Risk Analysis Schemas ---
class ExtractedEntityInput(BaseModel):
    clause_title: str
    entity_type: str
    entity_value: str
    normalized_value: str = ""
    confidence_score: float = 1.0

class RiskRuleInput(BaseModel):
    name: str
    description: Optional[str] = ""

class AnalyzeRequest(BaseModel):
    clauses: List[ClauseInput]
    extracted_entities: List[ExtractedEntityInput] = []
    risk_rules: List[RiskRuleInput] = []

class FindingOutput(BaseModel):
    clause_title: str
    risk_category: str
    risk_level: str
    explanation: str
    recommendation: str
    disadvantaged_party: Optional[str] = None

class EntityOutput(BaseModel):
    clause_title: str
    entity_type: str
    entity_value: str
    normalized_value: str = ""
    confidence_score: float = 1.0

class AnalyzeResponse(BaseModel):
    overall_score: int
    summary: str
    findings: List[FindingOutput]
    entities: List[EntityOutput] = []

# --- AI Summary Schemas ---
class SummarizeRequest(BaseModel):
    clauses: List[ClauseInput]
    contract_metadata: dict = {}

class SummarizeResponse(BaseModel):
    summary: str

# --- AI Extract Schemas ---
class EntityExtractRequest(BaseModel):
    text: str
    system_prompt: Optional[str] = None

class EntityExtractResponse(BaseModel):
    entities: dict
    raw_response: Optional[str] = None

class ClauseEntityExtractRequest(BaseModel):
    clauses: List[ClauseInput]

class ClauseEntityResult(BaseModel):
    clause_title: str
    entities: dict
    error: Optional[str] = None

class BatchEntityExtractResponse(BaseModel):
    results: List[ClauseEntityResult]

class ClauseExtractOutput(BaseModel):
    title: str
    content: str
    clause_type: Optional[str] = None

class ExtractClausesResponse(BaseModel):
    clauses: List[ClauseExtractOutput]


# 5. Core Inference Functions
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


# --- Core Risk Analysis Function ---
def run_ai_analysis(
    clauses: List[ClauseInput],
    extracted_entities: List[ExtractedEntityInput],
    risk_rules: List[RiskRuleInput] = [],
) -> AnalyzeResponse:
    findings = []
    total_score = 0
    scores_count = 0

    rules_instruction = ""
    if risk_rules:
        rules_instruction = "\n\nDanh sách các loại rủi ro hiện có trong hệ thống (hãy phân loại 'risk_category' trùng khớp với một trong số các tên này nếu điều khoản vi phạm, KHÔNG tự tạo thêm tên rủi ro mới nếu đã có sẵn tương đương):\n"
        for r in risk_rules:
            rules_instruction += f"- '{r.name}': {r.description or ''}\n"

    for c in clauses:
        prompt_content = f"Phân tích rủi ro cho điều khoản hợp đồng sau:\n\nTIÊU ĐỀ: {c.title}\nNỘI DUNG:\n{c.content}"
        prompt = [
            {
                "role": "system",
                "content": "Bạn là chuyên gia phân tích rủi ro hợp đồng pháp lý tại Việt Nam. "
                "Hãy đóng vai trò là một Luật sư cực kỳ nghiêm khắc, kỹ tính và luôn bảo vệ quyền lợi của Bên thuê/Bên mua. "
                "Nhiệm vụ của bạn là đọc kỹ điều khoản hợp đồng và phát hiện tất cả các lỗi, điểm bất lợi, rủi ro tiềm ẩn hoặc sự bất đối xứng quyền lợi. "
                "Hãy đảm bảo tất cả phần giải thích (explanation), khuyến nghị (recommendation) và phân loại rủi ro (risk_category) đều được viết hoàn toàn bằng tiếng Việt chuẩn xác. "
                "Luôn trả về JSON thuần túy với các trường sau: "
                "\"risk_category\" (str: Phân loại rủi ro bằng tiếng Việt, ví dụ: 'Rủi ro Giới hạn Trách nhiệm', 'Rủi ro Thanh toán', 'Điều khoản Chấm dứt Bất lợi', hoặc tên rủi ro phù hợp), "
                "\"severity\" (str: 'NONE', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'), "
                '"risk_score" (int 0-100), '
                '"explanation" (str: Giải thích chi tiết bằng tiếng Việt lý do điều khoản này có rủi ro hoặc bất lợi), '
                '"recommendation" (str: Đề xuất sửa đổi cụ thể bằng tiếng Việt để giảm thiểu rủi ro), '
                "\"disadvantaged_party\" (str: Bên gặp bất lợi, ví dụ 'Bên B', hoặc null). "
                f'Hãy suy luận cực kỳ chặt chẽ để tìm ra rủi ro. Nếu điều khoản thực sự hoàn toàn an toàn và không có bất kỳ rủi ro nào, hãy đặt "severity": "NONE", "risk_score": 0, "risk_category": "An toàn" và "disadvantaged_party": null.{rules_instruction}',
            },
            {"role": "user", "content": prompt_content},
        ]

        response = infer(prompt)

        try:
            parsed = clean_json(response)
            risk_cat = parsed.get("risk_category", "Rủi ro chung")
            severity = parsed.get("severity", "NONE")
            risk_score = int(parsed.get("risk_score", 0))
            explanation = parsed.get("explanation", "")
            recommendation = parsed.get("recommendation", "")
            disadvantaged = parsed.get("disadvantaged_party")

            if severity != "NONE":
                findings.append(
                    FindingOutput(
                        clause_title=c.title,
                        risk_category=risk_cat,
                        risk_level=severity,
                        explanation=explanation,
                        recommendation=recommendation,
                        disadvantaged_party=disadvantaged,
                    )
                )
                total_score += risk_score
                scores_count += 1
        except Exception as e:
            print(f"Error parsing model response for clause '{c.title}': {e}. Response was: {response}")

    overall_score = int(total_score / scores_count) if scores_count > 0 else 0
    summary = f"AI analysis completed. Scanned {len(clauses)} clauses. Found {len(findings)} risks."

    return AnalyzeResponse(
        overall_score=overall_score, summary=summary, findings=findings
    )


# 6. Endpoints
@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze_contract(payload: AnalyzeRequest):
    if not payload.clauses:
        raise HTTPException(status_code=400, detail="No clauses provided for analysis.")
    try:
        return run_ai_analysis(
            payload.clauses, payload.extracted_entities, payload.risk_rules
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")

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

ENTITY_SYSTEM_PROMPT = (
    "Bạn là hệ thống trích xuất thông tin hợp đồng tự động. "
    "Đọc đoạn văn bản (có thể là một điều khoản hợp đồng) và trích xuất các thông tin sau thành JSON. "
    "Chỉ điền giá trị nếu thực sự có trong văn bản, để chuỗi rỗng \"\" nếu không có:\n"
    "  COMPANY_NAME   : Tên công ty/tổ chức (có thể là list nếu nhiều bên)\n"
    "  TAX_CODE       : Mã số thuế\n"
    "  CONTRACT_VALUE : Giá trị hợp đồng (giữ nguyên đơn vị tiền tệ)\n"
    "  DATE_EFFECTIVE : Ngày hiệu lực (định dạng YYYY-MM-DD nếu có thể)\n"
    "  DATE_EXPIRE    : Ngày hết hạn (định dạng YYYY-MM-DD nếu có thể)\n"
    "  DURATION       : Thời hạn/thời gian thực hiện (ví dụ: '12 tháng', '2 năm')\n"
    "  PAYMENT_TERM   : Điều kiện/phương thức thanh toán\n"
    "  PENALTY        : Điều khoản phạt vi phạm (tóm tắt ngắn gọn)\n"
    "  OBLIGATION     : Nghĩa vụ chính của các bên (tóm tắt ngắn gọn)\n"
    "Chỉ trả về JSON hợp lệ, không giải thích gì thêm."
)

@app.post("/api/v1/extract_entities", response_model=EntityExtractResponse)
async def extract_entities(payload: EntityExtractRequest):
    sys_prompt = payload.system_prompt if payload.system_prompt else ENTITY_SYSTEM_PROMPT
    prompt = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": payload.text},
    ]
    try:
        response_text = infer(prompt)
        entities = clean_json(response_text)
        return EntityExtractResponse(entities=entities, raw_response=response_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/extract_entities_batch", response_model=BatchEntityExtractResponse)
async def extract_entities_batch(payload: ClauseEntityExtractRequest):
    """
    Extract entities từ danh sách clauses.
    Mỗi clause được xử lý riêng; kết quả trả về gắn kèm clause_title.
    """
    if not payload.clauses:
        raise HTTPException(status_code=400, detail="No clauses provided.")

    results: List[ClauseEntityResult] = []
    for clause in payload.clauses:
        text = f"[{clause.title}]\n{clause.content[:1000]}"
        prompt = [
            {"role": "system", "content": ENTITY_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]
        try:
            response_text = infer(prompt)
            entities = clean_json(response_text)
            results.append(ClauseEntityResult(
                clause_title=clause.title,
                entities=entities,
            ))
        except Exception as e:
            results.append(ClauseEntityResult(
                clause_title=clause.title,
                entities={},
                error=str(e),
            ))

    return BatchEntityExtractResponse(results=results)

@app.post("/api/v1/extract_clauses", response_model=ExtractClausesResponse)
async def extract_clauses(payload: EntityExtractRequest):
    if not payload.text:
        raise HTTPException(status_code=400, detail="No text provided.")
    prompt = [
        {
            "role": "system",
            "content": (
                "Bạn là chuyên gia phân tích văn bản pháp lý. Hãy phân tích văn bản hợp đồng sau "
                "và chia nó thành danh sách các điều khoản. "
                "Với mỗi điều khoản, trích xuất: "
                "1. title: Tiêu đề của điều khoản (ví dụ: 'Điều 1: Định nghĩa', 'Điều 2: Giá trị hợp đồng'). "
                "2. content: Nội dung chi tiết của điều khoản đó. "
                "3. clause_type: Thể loại điều khoản (ví dụ: 'Payment', 'Termination', 'Liability', 'Dispute', hoặc null nếu không rõ). "
                "Trả về kết quả dưới dạng một đối tượng JSON có thuộc tính \"clauses\" chứa danh sách các điều khoản nêu trên. "
                "Chỉ trả về JSON hợp lệ, không giải thích gì thêm."
            )
        },
        {"role": "user", "content": payload.text[:3000]}
    ]
    try:
        response_text = infer(prompt)
        data = clean_json(response_text)
        clauses = data.get("clauses", [])
        return ExtractClausesResponse(clauses=clauses)
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
    print(f"KAGGLE_QWEN_SERVICE_URL={public_url}")
    print(f"==================================================")
    import asyncio
    config = uvicorn.Config(app, host="0.0.0.0", port=8001)
    server = uvicorn.Server(config)
    await server.serve()
