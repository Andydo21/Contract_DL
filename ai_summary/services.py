import os
import logging
import requests
from fastapi import HTTPException
from schemas import SummarizeRequest, EntityExtractRequest

logger = logging.getLogger("ai_summary.services")

KAGGLE_AI_URL: str = os.environ.get("KAGGLE_AI_URL", "").rstrip("/")
REQUEST_TIMEOUT = 300  # 5-minute timeout

def get_kaggle_url() -> str:
    return KAGGLE_AI_URL

def require_kaggle_url():
    if not KAGGLE_AI_URL:
        raise HTTPException(
            status_code=503,
            detail=(
                "KAGGLE_AI_URL is not configured. "
                "Start the Kaggle notebook and paste the ngrok URL into .env."
            ),
        )

class AISummaryService:
    @staticmethod
    def summarize(payload: SummarizeRequest) -> dict:
        require_kaggle_url()
        url = f"{KAGGLE_AI_URL}/api/v1/summarize"
        logger.info(f"Forwarding summarize request → {url} ({len(payload.clauses)} clauses)")
        try:
            resp = requests.post(url, json=payload.model_dump(), timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"HTTP error calling Kaggle /api/v1/summarize: {e}")
            raise HTTPException(status_code=502, detail=f"Kaggle service error: {str(e)}")

    @staticmethod
    def extract_entities(payload: EntityExtractRequest) -> dict:
        require_kaggle_url()
        url = f"{KAGGLE_AI_URL}/api/v1/extract_entities"
        logger.info(f"Forwarding extract_entities request → {url}")
        try:
            resp = requests.post(url, json=payload.model_dump(), timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"HTTP error calling Kaggle /api/v1/extract_entities: {e}")
            raise HTTPException(status_code=502, detail=f"Kaggle service error: {str(e)}")
