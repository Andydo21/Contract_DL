"""
Kaggle Notebook Server - Logic HOÀN TOÀN dựa trên main.py
==========================================================
Chỉ khác main.py ở 2 điểm:
  1. Load merged model trực tiếp (float16, không cần 4-bit + PEFT)
     vì Kaggle có GPU T4 x2 đủ VRAM.
  2. Thêm ngrok để expose URL công khai.

Cách dùng:
  - Paste Cell 1 → Cell 4 lần lượt vào Kaggle notebook
  - Chạy tuần tự từng cell
  - Cell 4 in ra URL → copy vào docker-compose.yml: KAGGLE_AI_URL=<url>
"""

# =========================================================================
# CELL 1 - Cài thư viện
# =========================================================================
# !pip install -q fastapi uvicorn pyngrok

# =========================================================================
# CELL 2 - Load model (load merged model thẳng, không cần PEFT)
# =========================================================================
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch, json, re, logging, threading, uvicorn
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kaggle_ai_service")

MODEL_NAME = "Doan2108/contract-risk-qwen2.5-3b-merged"
HF_TOKEN = ""  # Set via Kaggle Secrets: Add HF_TOKEN in notebook secrets

# Global variables for model (giống main.py)
model = None
tokenizer = None

logger.info(f"Loading tokenizer for {MODEL_NAME}...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, token=HF_TOKEN)

# Kaggle có GPU T4 x2 (tổng ~32GB VRAM) → dùng float16 thay 4-bit
logger.info(f"Loading model {MODEL_NAME} with float16...")
model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    torch_dtype=torch.float16,
    device_map="auto",
    token=HF_TOKEN,
)
model.eval()
logger.info("Successfully loaded model!")


# =========================================================================
# CELL 3 - Schemas + Helper + Inference (copy từ main.py)
# =========================================================================


# --- Pydantic schemas (copy từ main.py) ---
class ClauseInput(BaseModel):
    title: str
    content: str


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


# --- copy từ main.py ---
def clean_and_parse_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    return json.loads(text)


# --- copy từ main.py (hàm _infer_local) ---
def _infer_local(messages: list) -> str:
    """Chạy inference trên GPU local bằng tokenizer + model.generate()."""
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

    generated_ids = outputs[0][input_ids.shape[1] :]
    return tokenizer.decode(generated_ids, skip_special_tokens=True)


# --- copy từ main.py (hàm run_ai_analysis) ---
def run_ai_analysis(
    clauses: List[ClauseInput],
    extracted_entities: List[ExtractedEntityInput],
    risk_rules: List[RiskRuleInput] = [],
) -> AnalyzeResponse:
    findings = []
    total_score = 0
    scores_count = 0

    # Format existing system risk rules to instruct the model to reuse them
    rules_instruction = ""
    if risk_rules:
        rules_instruction = "\n\nDanh sách các loại rủi ro hiện có trong hệ thống (hãy phân loại 'risk_category' trùng khớp với một trong số các tên này nếu điều khoản vi phạm, KHÔNG tự tạo thêm tên rủi ro mới nếu đã có sẵn tương đương):\n"
        for r in risk_rules:
            rules_instruction += f"- '{r.name}': {r.description or ''}\n"

    for c in clauses:
        prompt_content = f"Phân tích rủi ro cho điều khoản hợp đồng sau:\n\nTIÊU ĐỀ: {c.title}\nNỘI DUNG:\n{c.content}"

        # Prompt matching ChatML format used during Qwen fine-tuning
        prompt = [
            {
                "role": "system",
                "content": "Bạn là chuyên gia phân tích rủi ro hợp đồng pháp lý tại Việt Nam. "
                "Hãy đóng vai trò là một Luật sư cực kỳ nghiêm khắc, kỹ tính và luôn bảo vệ quyền lợi của Bên thuê/Bên mua. "
                "Nhiệm vụ của bạn là đọc kỹ điều khoản hợp đồng và phát hiện tất cả các lỗi, điểm bất lợi, rủi ro tiềm ẩn hoặc sự bất đối xứng quyền lợi. "
                "Luôn trả về JSON thuần túy với các trường sau: "
                "\"risk_category\" (str: Ví dụ 'Limitation of Liability Risk', 'Payment Risk', 'Unbalanced Termination Clause', hoặc tên rủi ro phù hợp), "
                "\"severity\" (str: 'NONE', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'), "
                '"risk_score" (int 0-100), '
                '"explanation" (str: Giải thích chi tiết bằng tiếng Việt lý do điều khoản này có rủi ro hoặc bất lợi), '
                '"recommendation" (str: Đề xuất sửa đổi cụ thể bằng tiếng Việt để giảm thiểu rủi ro), '
                "\"disadvantaged_party\" (str: Bên gặp bất lợi, ví dụ 'Bên B', hoặc null). "
                f'Hãy suy luận cực kỳ chặt chẽ để tìm ra rủi ro. Nếu điều khoản thực sự hoàn toàn an toàn và không có bất kỳ rủi ro nào, hãy đặt "severity": "NONE", "risk_score": 0, "risk_category": "Safe" và "disadvantaged_party": null.{rules_instruction}',
            },
            {"role": "user", "content": prompt_content},
        ]

        response = _infer_local(prompt)
        logger.info(f"Raw model response for '{c.title}': {response}")

        try:
            # Parse output JSON from assistant
            parsed = clean_and_parse_json(response)

            # Extract attributes
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
            logger.error(
                f"Error parsing model response for clause '{c.title}': {e}. Response was: {response}"
            )

    # Calculate overall score
    overall_score = int(total_score / scores_count) if scores_count > 0 else 0
    summary = f"AI analysis completed. Scanned {len(clauses)} clauses. Found {len(findings)} risks."

    return AnalyzeResponse(
        overall_score=overall_score, summary=summary, findings=findings
    )


# --- FastAPI app + endpoints (copy từ main.py) ---
app = FastAPI(title="RiskDL AI Inference Service", version="1.0.0")


@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze_contract(payload: AnalyzeRequest):
    if not payload.clauses:
        raise HTTPException(status_code=400, detail="No clauses provided for analysis.")
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="AI inference model is not loaded. Please wait for model loading to complete or check server logs.",
        )
    try:
        logger.info("Executing LLM model inference...")
        return run_ai_analysis(
            payload.clauses, payload.extracted_entities, payload.risk_rules
        )
    except Exception as e:
        logger.exception("Error during analysis:")
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")


@app.get("/health")
async def health_check():
    status = "healthy" if model is not None else "unhealthy"
    return {"status": status, "model_loaded": model is not None}


# Khởi động server trong background thread
threading.Thread(
    target=uvicorn.run,
    kwargs={"app": app, "host": "0.0.0.0", "port": 8000},
    daemon=True,
).start()

import time

time.sleep(3)
logger.info("✅ FastAPI server started on port 8000")


# =========================================================================
# CELL 4 - Expose qua ngrok → lấy URL công khai
# =========================================================================
# Đăng ký free tại https://ngrok.com → Dashboard → Authtoken → copy
from pyngrok import ngrok, conf

NGROK_TOKEN = "3Falm90byk0kDTynqQaVBJpyMOn_7QGUtEZT13zMKCej5qq65"
conf.get_default().auth_token = NGROK_TOKEN

url = ngrok.connect(8000, "http").public_url
print("=" * 65)
print(f"✅ KAGGLE AI SERVICE đang chạy tại: {url}")
print()
print("📋 Paste dòng sau vào docker-compose.yml (ai-service > environment):")
print(f"   - KAGGLE_AI_URL={url}")
print()
print("⚠️  Giữ notebook đang chạy! Tắt notebook = mất URL.")
print("=" * 65)
