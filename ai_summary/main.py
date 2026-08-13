import logging
import requests
from fastapi import FastAPI, HTTPException, Depends
from shared.jwt_middleware import fastapi_jwt_required
from schemas import (
    SummarizeRequest,
    SummarizeResponse,
    EntityExtractRequest,
    EntityExtractResponse,
)
from services import AISummaryService, get_kaggle_url

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_summary")

app = FastAPI(
    title="Kaggle Qwen AI Service",
    description=(
        "Proxy service that forwards requests to the Kaggle notebook running "
        "phamthanhfd/contract-analysis-qwen2.5-3b (4-bit) exposed via an ngrok tunnel."
    ),
    version="1.0.0",
)

@app.post("/api/v1/summarize", response_model=SummarizeResponse)
async def summarize_contract(payload: SummarizeRequest, jwt_payload: dict = Depends(fastapi_jwt_required)):
    """
    Forward to POST {KAGGLE_AI_URL}/api/v1/summarize.
    Kaggle notebook generates an Executive Summary in Vietnamese (150-250 words).
    """
    if not payload.clauses:
        raise HTTPException(status_code=400, detail="No clauses provided.")
    result = AISummaryService.summarize(payload)
    return SummarizeResponse(**result)

@app.post("/api/v1/extract_entities", response_model=EntityExtractResponse)
async def extract_entities(payload: EntityExtractRequest, jwt_payload: dict = Depends(fastapi_jwt_required)):
    """
    Forward to POST {KAGGLE_AI_URL}/api/v1/extract_entities.
    Kaggle notebook extracts: COMPANY_NAME, TAX_CODE, CONTRACT_VALUE,
    DATE_EFFECTIVE, DATE_EXPIRE from the given text.
    """
    if not payload.text:
        raise HTTPException(status_code=400, detail="No text provided.")
    result = AISummaryService.extract_entities(payload)
    return EntityExtractResponse(**result)

@app.get("/health")
async def health_check():
    """Health check – also pings the Kaggle notebook's /health endpoint."""
    kaggle_url = get_kaggle_url()
    configured = bool(kaggle_url)
    kaggle_status = None

    if configured:
        try:
            r = requests.get(f"{kaggle_url}/health", timeout=10)
            kaggle_status = r.json() if r.ok else {"error": r.text}
        except Exception as e:
            kaggle_status = {"error": str(e)}

    return {
        "status": "healthy" if configured else "degraded",
        "kaggle_url_configured": configured,
        "kaggle_url": kaggle_url or None,
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
