import sys
from pathlib import Path

# Add project root to sys.path to resolve shared package
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import os
import logging
import json
import re
import requests
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from shared.jwt_middleware import fastapi_jwt_required
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_service")

app = FastAPI(title="RiskDL AI Inference Service", version="1.0.0")

# Global configuration for Kaggle forwarding
kaggle_url = os.environ.get("KAGGLE_AI_URL", "").rstrip("/")  # URL ngrok từ Kaggle notebook

if kaggle_url:
    logger.info(f"✅ Kaggle mode: requests will forward to {kaggle_url}")
else:
    logger.error("❌ KAGGLE_AI_URL is not configured in .env! Local inference mode has been disabled.")


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
    """Forward toàn bộ request sang Kaggle / Local AI Service (ngrok URL)."""
    url = f"{kaggle_url.rstrip('/')}/api/v1/analyze"
    logger.info(f"Forwarding to AI Service: {url}")
    logger.info(f"--- REQUEST PAYLOAD ---\n{json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    headers = {
        "ngrok-skip-browser-warning": "true",
        "User-Agent": "RiskDL-Backend",
        "Content-Type": "application/json"
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=300)  # 5 phút timeout
    resp.raise_for_status()
    
    resp_json = resp.json()
    logger.info(f"--- RESPONSE PAYLOAD ---\n{json.dumps(resp_json, ensure_ascii=False, indent=2)}")
    return resp_json


def run_ai_analysis(
    clauses: List[ClauseInput],
    extracted_entities: List[ExtractedEntityInput],
    risk_rules: List[RiskRuleInput] = [],
) -> AnalyzeResponse:
    # --- Model Context Protocol (MCP) Integration ---
    try:
        from ai_service.mcp_client import MCPClient
        mcp_client = MCPClient()
        logger.info("Querying Legal MCP Server for legal references...")
        for c in clauses:
            ref_text = mcp_client.get_legal_references(c.title, c.content)
            if ref_text:
                c.content += ref_text
                logger.info(f"Successfully injected legal references into clause: '{c.title}'")
    except Exception as mcp_err:
        logger.warning(f"Error querying MCP server: {mcp_err}")

    # --- Kaggle mode: forward sang Kaggle server ---
    if not kaggle_url:
        raise ValueError("KAGGLE_AI_URL is not configured. Local inference has been disabled.")

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


@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze_contract(payload: AnalyzeRequest, jwt_payload: dict = Depends(fastapi_jwt_required)):
    if not payload.clauses:
        raise HTTPException(status_code=400, detail="No clauses provided for analysis.")

    if not kaggle_url:
        raise HTTPException(
            status_code=503,
            detail="KAGGLE_AI_URL is not configured in .env. Local inference is disabled.",
        )

    try:
        logger.info("Executing Kaggle LLM model inference...")
        return run_ai_analysis(
            payload.clauses, payload.extracted_entities, payload.risk_rules
        )
    except Exception as e:
        logger.exception("Error during analysis:")
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")


@app.get("/health")
async def health_check():
    status = "healthy" if kaggle_url else "unhealthy"
    return {"status": status, "kaggle_connected": bool(kaggle_url)}
