import sys
from pathlib import Path

# Add project root to sys.path to resolve shared package
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import logging
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import JSONResponse
from shared.jwt_middleware import fastapi_jwt_required
from schemas import CompareRequest, SummarizeRequest, SummarizeResponse
import llm
import services

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ai_summary')

app = FastAPI(
    title='Contract Summary Service',
    description='Structured, source-verified Vietnamese contract summaries from a vLLM-served text model.',
    version='2.0.0',
)


@app.post('/api/v1/summarize', response_model=SummarizeResponse)
def summarize_contract(payload: SummarizeRequest, jwt_payload: dict = Depends(fastapi_jwt_required)):
    # Sync endpoint: FastAPI runs it in a worker thread, so blocking model calls never stall the event loop.
    try:
        return services.summarize(payload.text, payload.contract_metadata, payload.force, payload.model,
                                  payload.perspective, payload.length, payload.explain_terms)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except llm.LLMError as error:
        logger.warning('summary model failed: %s', error)
        raise HTTPException(status_code=502, detail=str(error))


@app.post('/api/v1/compare')
def compare_versions(payload: CompareRequest, jwt_payload: dict = Depends(fastapi_jwt_required)):
    """Summaries of two versions (or a contract and its amended text) and the field-level changes."""
    try:
        return services.compare(payload.old_text, payload.new_text, payload.force, payload.model,
                                payload.perspective, payload.length, payload.explain_terms)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except llm.LLMError as error:
        logger.warning('summary model failed: %s', error)
        raise HTTPException(status_code=502, detail=str(error))


@app.post('/api/v1/prepare')
def prepare_contract(payload: SummarizeRequest, jwt_payload: dict = Depends(fastapi_jwt_required)):
    """Sections, facts and chunk plan for a text; no model call."""
    return services.prepare(payload.text)


@app.get('/health')
def health_check():
    connected = llm.is_connected()
    return JSONResponse({
        'status': 'healthy' if connected else 'degraded',
        'llm_url': llm.base_url() or None,
        'model': llm.model_id(),
        'llm_connected': connected,
    }, status_code=200 if connected else 503)


@app.get('/')
def root():
    return {'service': 'Contract Summary Service', 'version': '2.0.0', 'model': llm.model_id(),
            'endpoints': ['POST /api/v1/summarize', 'POST /api/v1/compare', 'POST /api/v1/prepare', 'GET  /health'], 'docs': '/docs'}
