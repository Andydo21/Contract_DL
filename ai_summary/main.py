import sys
from pathlib import Path

# Add project root to sys.path to resolve shared package
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import json
import logging
from fastapi import FastAPI, HTTPException, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse
from shared.jwt_middleware import fastapi_jwt_required
from schemas import CompareRequest, RenderOptions, SummarizeRequest, SummarizeResponse
import insights
import llm
import reader
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


def read_upload(upload: UploadFile) -> dict:
    try:
        return services.read_document(upload.file.read(), upload.filename or '')
    except reader.ReadError as error:
        raise HTTPException(status_code=422, detail=str(error))


def form_options(perspective, length, explain_terms):
    try:
        return RenderOptions(perspective=perspective, length=length, explain_terms=explain_terms)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


def source_info(document):
    """What was read from the file, without the text itself."""
    return {k: v for k, v in document.items() if k != 'text'}


@app.post('/api/v1/read')
def read_file(file: UploadFile = File(...), jwt_payload: dict = Depends(fastapi_jwt_required)):
    """Text read from a PDF/DOCX/TXT file plus the chunk plan; no model call."""
    document = read_upload(file)
    return {'source': source_info(document), 'text': document['text'], 'prepare': services.prepare(document['text']),
            'preliminary': insights.preliminary(document['text']), 'suggest': insights.suggest(document['text'])}


@app.post('/api/v1/sections')
def file_sections(file: UploadFile = File(...), jwt_payload: dict = Depends(fastapi_jwt_required)):
    """Clause text by the label summaries cite ("Điều 3"), so a citation can open the source; no model call."""
    return {'sections': services.sections_by_label(read_upload(file)['text'])}


@app.post('/api/v1/summarize-file')
def summarize_file(file: UploadFile = File(...), perspective: str = Form('general'), length: str = Form('detailed'),
                   explain_terms: bool = Form(False), force: bool = Form(False), model: str | None = Form(None),
                   contract_metadata: str = Form('{}'), jwt_payload: dict = Depends(fastapi_jwt_required)):
    """Read the file here (no other extraction service involved) and summarize it."""
    options = form_options(perspective, length, explain_terms)
    document = read_upload(file)
    try:
        metadata = json.loads(contract_metadata or '{}')
        result = services.summarize(document['text'], metadata, force, model,
                                    options.perspective, options.length, options.explain_terms)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except llm.LLMError as error:
        logger.warning('summary model failed: %s', error)
        raise HTTPException(status_code=502, detail=str(error))
    return {**result, 'source': source_info(document)}


@app.post('/api/v1/compare-files')
def compare_files(old_file: UploadFile = File(...), new_file: UploadFile = File(...), perspective: str = Form('general'),
                  length: str = Form('detailed'), explain_terms: bool = Form(False), force: bool = Form(False),
                  model: str | None = Form(None), jwt_payload: dict = Depends(fastapi_jwt_required)):
    options = form_options(perspective, length, explain_terms)
    old, new = read_upload(old_file), read_upload(new_file)
    try:
        result = services.compare(old['text'], new['text'], force, model,
                                  options.perspective, options.length, options.explain_terms)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except llm.LLMError as error:
        logger.warning('summary model failed: %s', error)
        raise HTTPException(status_code=502, detail=str(error))
    return {**result, 'old_source': source_info(old), 'new_source': source_info(new)}


@app.get('/health')
def health_check():
    connected = llm.is_connected()
    return JSONResponse({
        'status': 'healthy' if connected else 'degraded',
        'llm_url': llm.base_url() or None,
        'model': llm.model_id(),
        'llm_connected': connected,
        'ocr_available': reader.ocr_available(),
    }, status_code=200 if connected else 503)


@app.get('/')
def root():
    return {'service': 'Contract Summary Service', 'version': '2.0.0', 'model': llm.model_id(),
            'endpoints': ['POST /api/v1/summarize-file', 'POST /api/v1/compare-files', 'POST /api/v1/read',
                          'POST /api/v1/summarize', 'POST /api/v1/compare', 'POST /api/v1/prepare', 'GET  /health'],
            'docs': '/docs'}
