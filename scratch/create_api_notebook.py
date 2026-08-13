import json
import textwrap

# ── Cell sources (plain Python strings — no JSON escaping needed here) ─────────

CELL_INSTALL = """\
# Cell 1: Install dependencies
!pip install -q fastapi uvicorn pyngrok nest_asyncio transformers torch sentencepiece protobuf accelerate
"""

CELL_APP = """\
# Cell 2: Imports, model loading, FastAPI app + endpoint
import os, nest_asyncio, uvicorn, torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from pyngrok import ngrok
from transformers import AutoModelForSequenceClassification, AutoModelForSeq2SeqLM, AutoTokenizer

nest_asyncio.apply()
app = FastAPI(title="Unified Kaggle Workflow Recommendation Service")
device = "cuda" if torch.cuda.is_available() else "cpu"

# ── 1. Classification model (DeBERTa) ─────────────────────────────────────────
# Load d90nqm/contract-workflow directly from HuggingFace Hub
# Classifies contracts into 8 types: WF_NDA, WF_SERVICE, WF_EMPLOYMENT, ...
DEBERTA_HF_ID = "d90nqm/contract-workflow"
print(f"Loading classification model: {DEBERTA_HF_ID} ...")
try:
    deberta_tokenizer = AutoTokenizer.from_pretrained(DEBERTA_HF_ID)
    deberta_model = AutoModelForSequenceClassification.from_pretrained(DEBERTA_HF_ID)
    deberta_model.eval().to(device)
    print(f"Classification model loaded! Labels: {list(deberta_model.config.id2label.values())}")
except Exception as e:
    print(f"Failed to load classification model: {e}")
    deberta_model = None

# ── 2. Step-generation model (Flan-T5) ────────────────────────────────────────
# Generates approval step sequence AND dynamic descriptions/reasons
FLANT5_PATH = "Doan2108/dynamic_worflow"
print(f"Loading Flan-T5 step builder: {FLANT5_PATH} ...")
try:
    flant5_tokenizer = AutoTokenizer.from_pretrained(FLANT5_PATH)
    flant5_model = AutoModelForSeq2SeqLM.from_pretrained(FLANT5_PATH)
    flant5_model.eval().to(device)
    print("Flan-T5 model loaded successfully!")
except Exception as e:
    print(f"Failed to load Flan-T5 ({e}). Falling back to google/flan-t5-base ...")
    try:
        flant5_tokenizer = AutoTokenizer.from_pretrained("google/flan-t5-base")
        flant5_model = AutoModelForSeq2SeqLM.from_pretrained("google/flan-t5-base")
        flant5_model.eval().to(device)
        print("Fallback Flan-T5 base loaded.")
    except Exception as e2:
        print(f"Fallback also failed: {e2}")
        flant5_model = None

# ── Step library: name -> role_id + fallback description ──────────────────────
STEP_DETAILS_MAPPING = {
    "Contract Negotiation": {"role_id": 4,  "description": "Thuong thao cac dieu khoan chua thong nhat giua cac ben ky ket."},
    "Legal Review":         {"role_id": 4,  "description": "Ra soat tinh phap ly, rui ro dieu khoan va tuan thu phap luat."},
    "Technical Review":     {"role_id": 7,  "description": "Tham dinh tinh kha thi ky thuat va giai phap cong nghe de xuat."},
    "Security Review":      {"role_id": 8,  "description": "Danh gia an toan thong tin, bao mat du lieu va he thong."},
    "Compliance Review":    {"role_id": 9,  "description": "Kiem tra su tuan thu cac quy dinh noi bo va tieu chuan nganh."},
    "Finance Review":       {"role_id": 6,  "description": "Tham dinh ngan sach, dong tien va nghia vu tai chinh phat sinh."},
    "Procurement Review":   {"role_id": 10, "description": "Danh gia nang luc nha cung cap, don gia va chinh sach mua sam."},
    "Manager Approval":     {"role_id": 5,  "description": "Phe duyet cap quan ly truc tiep ve mat chu truong va ngan sach."},
    "Director Approval":    {"role_id": 11, "description": "Phe duyet cap Giam doc bo phan doi voi cac hop dong/du an lon."},
    "Executive Approval":   {"role_id": 11, "description": "Phe duyet toi cao tu Ban dieu hanh/Tong giam doc."},
    "Contract Signing":     {"role_id": 4,  "description": "Dai dien co tham quyen thuc hien ky ket hop dong chinh thuc."},
    "Document Archive":     {"role_id": 4,  "description": "Luu tru hop dong da ky ket vao he thong va ban giao ban cung."},
}

# ── Pydantic schemas ───────────────────────────────────────────────────────────
class RecommendWorkflowRequest(BaseModel):
    contract_text: str
    clause_types: List[str] = []
    contract_type: str = ""

class WorkflowStepResponse(BaseModel):
    step_name: str
    role_id: int
    description: str

class RecommendWorkflowResponse(BaseModel):
    workflow_type: str
    steps: List[WorkflowStepResponse]
    reasons: str
    workflow_name: Optional[str] = None

# ── Helper: call Flan-T5 ───────────────────────────────────────────────────────
def flan_generate(prompt: str, max_new_tokens: int = 100) -> str:
    if flant5_model is None:
        return ""
    enc = flant5_tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512).to(device)
    with torch.no_grad():
        out = flant5_model.generate(**enc, max_new_tokens=max_new_tokens)
    return flant5_tokenizer.decode(out[0], skip_special_tokens=True).strip()

# ── Endpoints ──────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "healthy",
        "deberta": deberta_model is not None,
        "flant5": flant5_model is not None,
        "device": device,
    }

@app.post("/api/v1/recommend_workflow", response_model=RecommendWorkflowResponse)
async def recommend_workflow_api(payload: RecommendWorkflowRequest):
    context = payload.contract_text[:300]

    # ── Step A: Classify workflow type ────────────────────────────────────────
    workflow_type = "WF_GENERAL"
    confidence = 0.0
    if deberta_model is not None:
        try:
            enc = deberta_tokenizer(
                payload.contract_text,
                return_tensors="pt",
                truncation=True,
                max_length=512,
            ).to(device)
            with torch.no_grad():
                logits = deberta_model(**enc).logits
            pred_idx = int(torch.argmax(logits, dim=-1).item())
            confidence = float(torch.softmax(logits, dim=-1)[0][pred_idx].item())
            workflow_type = deberta_model.config.id2label.get(pred_idx, "WF_GENERAL")
            print(f"[CLASSIFY] {workflow_type}  confidence={confidence:.1%}")
        except Exception as e:
            print(f"Classification error: {e}")

    # ── Step B: AI-generated explanation (reasons) ────────────────────────────
    wf_label = workflow_type.replace("WF_", "").replace("_", " ").title()
    reason_prompt = (
        f"Based on this contract: '{context}...', "
        f"explain in 1 Vietnamese sentence why it is classified as a '{wf_label}' contract workflow:"
    )
    reasons = flan_generate(reason_prompt, max_new_tokens=120)
    if len(reasons) < 10:
        reasons = (
            f"Mo hinh AI phan loai hop dong nay la '{wf_label}' "
            f"voi do tin cay {confidence:.1%}."
        )

    # ── Step C: Generate approval step sequence ───────────────────────────────
    steps_list = []
    step_prompt = "Generate the contract workflow steps for: " + payload.contract_text
    decoded = flan_generate(step_prompt, max_new_tokens=64)
    parsed_steps = [s.strip() for s in decoded.split("->") if s.strip()]

    for step_name in parsed_steps:
        if step_name not in STEP_DETAILS_MAPPING:
            continue
        details = STEP_DETAILS_MAPPING[step_name]

        # Dynamic per-step description from Flan-T5
        desc_prompt = (
            f"Based on this contract: '{context}...', "
            f"explain the approval step '{step_name}' in 1 short Vietnamese sentence:"
        )
        dynamic_desc = flan_generate(desc_prompt, max_new_tokens=64)
        if len(dynamic_desc) < 5:
            dynamic_desc = details["description"]

        steps_list.append(WorkflowStepResponse(
            step_name=step_name,
            role_id=details["role_id"],
            description=dynamic_desc,
        ))

    # ── Step D: Fallback steps if generation failed ───────────────────────────
    if not steps_list:
        for step_name in ["Legal Review", "Manager Approval", "Contract Signing", "Document Archive"]:
            d = STEP_DETAILS_MAPPING[step_name]
            steps_list.append(WorkflowStepResponse(
                step_name=step_name,
                role_id=d["role_id"],
                description=d["description"],
            ))

    workflow_name = f"{wf_label} Contract Approval Workflow"
    return RecommendWorkflowResponse(
        workflow_type=workflow_type,
        steps=steps_list,
        reasons=reasons,
        workflow_name=workflow_name,
    )
"""

CELL_NGROK = """\
# Cell 3: Start Ngrok tunnel + Uvicorn server
# NOTE: Kaggle/Jupyter already has a running event loop.
# Use uvicorn.Server + await instead of uvicorn.run() to avoid RuntimeError.
import asyncio

NGROK_TOKEN = os.environ.get("NGROK_AUTH_TOKEN", "2z2Jys005c289EvZifDWi1ViBBr_7nZ6ASrHHT7qpoJ3DgmQU")
ngrok.set_auth_token(NGROK_TOKEN)
try:
    tunnel = ngrok.connect(8000)
    print("\\n" + "="*60)
    print("  NGROK PUBLIC URL  (copy -> KAGGLE_AI_URL in .env):")
    print(f"  {tunnel.public_url}")
    print("="*60 + "\\n")
except Exception as e:
    print(f"Ngrok tunnel failed: {e}")

config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
server = uvicorn.Server(config)
await server.serve()
"""

# ── Build notebook JSON ────────────────────────────────────────────────────────
def make_code_cell(source: str):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [line + "\n" for line in source.rstrip("\n").split("\n")],
    }

notebook = {
    "cells": [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "# Unified Workflow Recommendation API Server\n",
                "\n",
                "Loads **d90nqm/contract-workflow** (DeBERTa, 8-class) from HuggingFace to classify contracts,\n",
                "then uses **Flan-T5** to:\n",
                "- generate the ordered approval step sequence\n",
                "- generate a Vietnamese explanation (`reasons`) for the classification\n",
                "- generate a context-aware Vietnamese description for each step\n",
            ],
        },
        make_code_cell(CELL_INSTALL),
        make_code_cell(CELL_APP),
        make_code_cell(CELL_NGROK),
    ],
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.10.0"},
    },
    "nbformat": 4,
    "nbformat_minor": 4,
}

with open("workflow-api-server.ipynb", "w", encoding="utf-8") as f:
    json.dump(notebook, f, indent=1, ensure_ascii=False)

print("[OK] workflow-api-server.ipynb regenerated successfully!")
