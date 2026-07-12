import os
import logging
import requests
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ─────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kaggle_qwen_service")

app = FastAPI(
    title="Kaggle Qwen AI Service",
    description=(
        "Proxy service that forwards requests to the Kaggle notebook running "
        "phamthanhfd/contract-analysis-qwen2.5-3b (4-bit) exposed via an ngrok tunnel."
    ),
    version="1.0.0",
)

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────
# Public ngrok URL printed by the Kaggle notebook.
# Example: https://xxxx-xx-xx-xx-xx.ngrok-free.app
KAGGLE_AI_URL: str = os.environ.get("KAGGLE_AI_URL", "").rstrip("/")

if not KAGGLE_AI_URL:
    logger.warning(
        "⚠️  KAGGLE_AI_URL is not set. "
        "Run the Kaggle notebook, copy the ngrok public URL it prints "
        "and set it as KAGGLE_AI_URL in .env. "
        "All API calls will fail until this is configured."
    )
else:
    logger.info(f"✅ Forwarding requests to Kaggle AI at: {KAGGLE_AI_URL}")

REQUEST_TIMEOUT = 300  # 5-minute timeout – model inference can be slow


# ─────────────────────────────────────────────────────────────
# Pydantic schemas  (mirrors kaggle_notebook.py exactly)
# ─────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────
# Helper – raise 503 if not configured
# ─────────────────────────────────────────────────────────────
def _require_kaggle_url():
    if not KAGGLE_AI_URL:
        raise HTTPException(
            status_code=503,
            detail=(
                "KAGGLE_AI_URL is not configured. "
                "Start the Kaggle notebook and paste the ngrok URL into .env."
            ),
        )


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────
@app.post("/api/v1/summarize", response_model=SummarizeResponse)
async def summarize_contract(payload: SummarizeRequest):
    """
    Forward to POST {KAGGLE_AI_URL}/api/v1/summarize.
    Kaggle notebook generates an Executive Summary in Vietnamese (150-250 words).
    """
    _require_kaggle_url()

    if not payload.clauses:
        raise HTTPException(status_code=400, detail="No clauses provided.")

    url = f"{KAGGLE_AI_URL}/api/v1/summarize"
    logger.info(f"Forwarding summarize request → {url} ({len(payload.clauses)} clauses)")

    try:
        resp = requests.post(
            url,
            json=payload.model_dump(),
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return SummarizeResponse(**resp.json())
    except requests.RequestException as e:
        logger.error(f"HTTP error calling Kaggle /api/v1/summarize: {e}")
        raise HTTPException(status_code=502, detail=f"Kaggle service error: {str(e)}")


@app.post("/api/v1/extract_entities", response_model=EntityExtractResponse)
async def extract_entities(payload: EntityExtractRequest):
    """
    Forward to POST {KAGGLE_AI_URL}/api/v1/extract_entities.
    Kaggle notebook extracts: COMPANY_NAME, TAX_CODE, CONTRACT_VALUE,
    DATE_EFFECTIVE, DATE_EXPIRE from the given text.
    """
    _require_kaggle_url()

    if not payload.text:
        raise HTTPException(status_code=400, detail="No text provided.")

    url = f"{KAGGLE_AI_URL}/api/v1/extract_entities"
    logger.info(f"Forwarding extract_entities request → {url}")

    try:
        resp = requests.post(
            url,
            json=payload.model_dump(),
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return EntityExtractResponse(**resp.json())
    except requests.RequestException as e:
        logger.error(f"HTTP error calling Kaggle /api/v1/extract_entities: {e}")
        raise HTTPException(status_code=502, detail=f"Kaggle service error: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check – also pings the Kaggle notebook's /health endpoint."""
    configured = bool(KAGGLE_AI_URL)
    kaggle_status = None

    if configured:
        try:
            r = requests.get(f"{KAGGLE_AI_URL}/health", timeout=10)
            kaggle_status = r.json() if r.ok else {"error": r.text}
        except Exception as e:
            kaggle_status = {"error": str(e)}

    return {
        "status": "healthy" if configured else "degraded",
        "kaggle_url_configured": configured,
        "kaggle_url": KAGGLE_AI_URL or None,
        "kaggle_health": kaggle_status,
    }


@app.get("/")
async def root():
    return {
        "service": "Kaggle Qwen AI Service",
        "version": "1.0.0",
        "model": "phamthanhfd/contract-analysis-qwen2.5-3b (4-bit)",
        "tunnel": "ngrok",
        "endpoints": [
            "POST /api/v1/summarize",
            "POST /api/v1/extract_entities",
            "GET  /health",
        ],
        "docs": "/docs",
    }
