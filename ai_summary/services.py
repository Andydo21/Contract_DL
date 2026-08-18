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
        req_data = payload.model_dump()
        import json
        logger.info(f"Forwarding summarize request → {url} ({len(payload.clauses)} clauses)")
        logger.info(f"--- KAGLGE SUMMARIZE REQUEST PAYLOAD ---\n{json.dumps(req_data, ensure_ascii=False, indent=2)}")
        try:
            resp = requests.post(url, json=req_data, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            resp_json = resp.json()
            logger.info(f"--- KAGGLE SUMMARIZE RESPONSE PAYLOAD ---\n{json.dumps(resp_json, ensure_ascii=False, indent=2)}")
            return resp_json
        except requests.RequestException as e:
            logger.error(f"HTTP error calling Kaggle /api/v1/summarize: {e}")
            raise HTTPException(status_code=502, detail=f"Kaggle service error: {str(e)}")

    @staticmethod
    def extract_entities(payload: EntityExtractRequest) -> dict:
        require_kaggle_url()
        url = f"{KAGGLE_AI_URL}/api/v1/extract_entities"
        req_data = payload.model_dump()
        import json
        logger.info(f"Forwarding extract_entities request → {url}")
        logger.info(f"--- KAGLGE EXTRACT REQUEST PAYLOAD ---\n{json.dumps(req_data, ensure_ascii=False, indent=2)}")
        try:
            resp = requests.post(url, json=req_data, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            resp_json = resp.json()
            logger.info(f"--- KAGGLE EXTRACT RESPONSE PAYLOAD ---\n{json.dumps(resp_json, ensure_ascii=False, indent=2)}")
            return resp_json
        except requests.RequestException as e:
            logger.error(f"HTTP error calling Kaggle /api/v1/extract_entities: {e}")
            raise HTTPException(status_code=502, detail=f"Kaggle service error: {str(e)}")
