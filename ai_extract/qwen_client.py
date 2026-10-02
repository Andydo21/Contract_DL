"""Qwen client for the dual Kaggle gateway and the legacy custom API."""
from __future__ import annotations

import json
import os
import re

import requests
from django.conf import settings


NGROK_HEADERS = {"ngrok-skip-browser-warning": "true"}
DEFAULT_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct-AWQ"
REQUEST_TIMEOUT = 300


ENTITY_SYSTEM_PROMPT = (
    "Bạn là hệ thống trích xuất thông tin hợp đồng tự động. Đọc văn bản và "
    "chỉ trả về một JSON object hợp lệ với các khóa COMPANY_NAME, TAX_CODE, "
    "CONTRACT_VALUE, DATE_EFFECTIVE, DATE_EXPIRE, DURATION, PAYMENT_TERM, "
    "PENALTY, OBLIGATION. Dùng chuỗi rỗng nếu thông tin không xuất hiện."
)

CLAUSE_SYSTEM_PROMPT = (
    "Bạn là chuyên gia phân tích văn bản pháp lý. Chia văn bản thành các điều "
    "khoản và chỉ trả về JSON hợp lệ dạng "
    '{"clauses":[{"title":"...","content":"...","clause_type":null}]}. '
    "Không thêm markdown hoặc giải thích."
)


class QwenGatewayError(RuntimeError):
    pass


def request_qwen(task: str, payload: dict) -> dict:
    """Call notebook /v1/chat/completions, or fall back to the legacy API."""
    vllm_base = _vllm_base_url()
    if vllm_base:
        return _request_openai_compatible(vllm_base, task, payload)
    return _request_legacy(task, payload)


def _request_openai_compatible(base_url: str, task: str, payload: dict) -> dict:
    if task == "summarize":
        clauses = payload.get("clauses", [])[:15]
        contract_text = "\n\n".join(
            f"[{item.get('title', '')}]\n{item.get('content', '')[:800]}" for item in clauses
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "Bạn là chuyên gia pháp lý. Viết tóm tắt điều hành bằng tiếng Việt, "
                    "150-250 từ, gồm mục đích, các bên, giá trị, thời hạn, nghĩa vụ và rủi ro."
                ),
            },
            {"role": "user", "content": f"NỘI DUNG HỢP ĐỒNG:\n{contract_text}"},
        ]
        return {"summary": _chat(base_url, messages, max_tokens=700).strip()}

    if task == "extract_entities":
        messages = [
            {"role": "system", "content": ENTITY_SYSTEM_PROMPT},
            {"role": "user", "content": payload.get("text", "")},
        ]
        data = _parse_json_object(_chat(base_url, messages, max_tokens=900))
        if isinstance(data.get("entities"), dict):
            data = data["entities"]
        return {"entities": data}

    if task == "extract_clauses":
        messages = [
            {"role": "system", "content": CLAUSE_SYSTEM_PROMPT},
            {"role": "user", "content": payload.get("text", "")[:7000]},
        ]
        data = _parse_json_object(_chat(base_url, messages, max_tokens=1800))
        return {"clauses": data.get("clauses", [])}

    raise QwenGatewayError(f"Unsupported Qwen task: {task}")


def _chat(base_url: str, messages: list[dict], max_tokens: int = 2048) -> str:
    model = os.environ.get("QWEN_MODEL_ID") or getattr(
        settings, "QWEN_MODEL_ID", DEFAULT_MODEL
    )
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": max_tokens,
            },
            headers=NGROK_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
        raise QwenGatewayError(f"Qwen /v1/chat/completions error: {exc}") from exc


def _request_legacy(task: str, payload: dict) -> dict:
    base_url = getattr(settings, "KAGGLE_QWEN_SERVICE_URL", "").rstrip("/")
    if not base_url:
        raise QwenGatewayError("VLLM_BASE_URL and KAGGLE_QWEN_SERVICE_URL are not configured")
    endpoint = {
        "summarize": "/api/v1/summarize",
        "extract_entities": "/api/v1/extract_entities",
        "extract_clauses": "/api/v1/extract_clauses",
    }.get(task)
    if not endpoint:
        raise QwenGatewayError(f"Unsupported Qwen task: {task}")
    try:
        response = requests.post(
            f"{base_url}{endpoint}",
            json=payload,
            headers=NGROK_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise QwenGatewayError(f"Qwen legacy endpoint {endpoint} error: {exc}") from exc


def _vllm_base_url() -> str:
    configured = os.environ.get("VLLM_BASE_URL") or getattr(settings, "VLLM_BASE_URL", "")
    if configured:
        return configured.rstrip("/")
    colpali = os.environ.get("COLPALI_BASE_URL") or getattr(
        settings, "COLPALI_BASE_URL", ""
    )
    if colpali and colpali.rstrip("/").endswith("/colpali"):
        return colpali.rstrip("/")[:-len("/colpali")] + "/v1"
    return ""


def _parse_json_object(content: str) -> dict:
    cleaned = (content or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()
    else:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start:end + 1]
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise QwenGatewayError(f"Qwen returned invalid JSON: {exc}") from exc
    if not isinstance(result, dict):
        raise QwenGatewayError("Qwen response must be a JSON object")
    return result
