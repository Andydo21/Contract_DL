import os
import logging
import json
import re
import requests
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_service")

app = FastAPI(title="RiskDL AI Inference Service", version="1.0.0")

# Global variables for model
model = None
tokenizer = None

# Configure environment and parameters
kaggle_url = os.environ.get("KAGGLE_AI_URL", "").rstrip("/")  # URL ngrok từ Kaggle notebook
model_id   = os.environ.get("BASE_MODEL_NAME", "Qwen/Qwen2.5-3B-Instruct")
adapter_id = os.environ.get("ADAPTER_MODEL_NAME", "Doan2108/contract-risk-qwen2.5-3b-fix1")
hf_token   = os.environ.get("HF_TOKEN", "")

if kaggle_url:
    # Chế độ Kaggle: không load model local, chỉ forward request
    model = "kaggle"  # truthy để health check pass
    logger.info(f"✅ Kaggle mode: requests will forward to {kaggle_url}")
else:
    # Chế độ Local: load model + PEFT adapter 4-bit trên GPU
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from peft import PeftModel

        logger.info(f"Loading tokenizer for {model_id}...")
        tokenizer = AutoTokenizer.from_pretrained(model_id, token=hf_token)

        # Configure 4-bit quantization to fit on 4GB VRAM GPU
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        )

        logger.info(f"Loading base model {model_id}...")
        try:
            base_model = AutoModelForCausalLM.from_pretrained(
                model_id,
                quantization_config=bnb_config,
                device_map="auto" if torch.cuda.is_available() else None,
                token=hf_token,
            )
        except Exception as q_err:
            logger.warning(f"Could not load with 4-bit quantization, falling back: {q_err}")
            base_model = AutoModelForCausalLM.from_pretrained(
                model_id,
                device_map="auto" if torch.cuda.is_available() else None,
                token=hf_token,
            )

        logger.info(f"Loading PEFT adapter {adapter_id}...")
        model = PeftModel.from_pretrained(base_model, adapter_id, token=hf_token)
        model.eval()
        logger.info("Successfully loaded base model + LoRA adapter!")
    except Exception as e:
        logger.error(f"Failed to load model: {e}")


# Pydantic schemas
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


def _forward_to_kaggle(payload: dict) -> dict:
    """Forward toàn bộ request sang Kaggle AI Service (ngrok URL)."""
    url = f"{kaggle_url}/api/v1/analyze"
    logger.info(f"Forwarding to Kaggle: {url}")
    resp = requests.post(url, json=payload, timeout=300)  # 5 phút timeout
    resp.raise_for_status()
    return resp.json()


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
    input_ids      = inputs["input_ids"].to(device)
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


# Real AI inference runner using fine-tuned model
def run_ai_analysis(
    clauses: List[ClauseInput],
    extracted_entities: List[ExtractedEntityInput],
    risk_rules: List[RiskRuleInput] = [],
) -> AnalyzeResponse:
    # --- Kaggle mode: forward sang Kaggle server ---
    if kaggle_url:
        payload = {
            "clauses":            [{"title": c.title, "content": c.content} for c in clauses],
            "extracted_entities": [],
            "risk_rules":         [{"name": r.name, "description": r.description} for r in risk_rules],
        }
        result   = _forward_to_kaggle(payload)
        findings = [FindingOutput(**f) for f in result.get("findings", [])]
        return AnalyzeResponse(
            overall_score=result.get("overall_score", 0),
            summary=result.get("summary", ""),
            findings=findings,
        )

    # --- Local mode: chạy trực tiếp trên GPU ---
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
