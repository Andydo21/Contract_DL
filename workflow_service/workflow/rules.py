import os
import re
import unicodedata
import requests


def clean_contract_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00a0", " ")
    text = "".join(ch for ch in text if ch in "\n\t" or ch >= " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# Default fallback steps when AI is unavailable
DEFAULT_STEPS = [
    {"step_name": "Legal Review",     "role_id": 4, "description": "Rà soát tính pháp lý, rủi ro điều khoản và tuân thủ pháp luật."},
    {"step_name": "Manager Approval", "role_id": 5, "description": "Phê duyệt cấp quản lý trực tiếp về mặt chủ trương và ngân sách."},
    {"step_name": "Contract Signing", "role_id": 4, "description": "Đại diện có thẩm quyền thực hiện ký kết hợp đồng chính thức."},
    {"step_name": "Document Archive", "role_id": 4, "description": "Lưu trữ hợp đồng đã ký kết vào hệ thống và bàn giao bản cứng."},
]


def recommend_workflow(text: str, clause_types: list, contract_type: str):
    """
    Calls the external Kaggle AI service (via Ngrok) to recommend a workflow.
    Falls back to a minimal default if the AI service is unreachable.

    Returns: (workflow_type, steps_list, reasons_str, ai_workflow_name)
    """
    clean_text = clean_contract_text(text)
    signals = [clean_contract_text(c) for c in clause_types if c]
    declared_type = clean_contract_text(contract_type)

    # Build list of URLs to try — KAGGLE_AI_URL has highest priority
    kaggle_url = os.environ.get("KAGGLE_AI_URL", "").rstrip("/")
    ai_service_url = os.environ.get("AI_SERVICE_URL", "").rstrip("/")

    urls_to_try = []
    if kaggle_url:
        urls_to_try.append(kaggle_url)
    if ai_service_url:
        urls_to_try.append(ai_service_url)
    # Local fallbacks
    urls_to_try += ["http://ai-service:8000", "http://localhost:8001"]

    # Deduplicate while preserving order
    seen = set()
    unique_urls = [u for u in urls_to_try if u and not (u in seen or seen.add(u))]

    for url in unique_urls:
        endpoint = f"{url}/api/v1/recommend_workflow"
        try:
            from shared.jwt_middleware import get_system_auth_header
            resp = requests.post(
                endpoint,
                json={
                    "contract_text": clean_text,
                    "clause_types": signals,
                    "contract_type": declared_type,
                },
                headers=get_system_auth_header(),
                timeout=60,  # Kaggle model may take time on first inference
            )
            if resp.status_code == 200:
                data = resp.json()
                workflow_type = data.get("workflow_type", "WF_GENERAL")
                steps = data.get("steps", [])
                reasons = data.get("reasons", "")
                workflow_name = data.get("workflow_name")
                return workflow_type, steps, reasons, workflow_name
        except Exception:
            continue

    # Fallback: AI unreachable — return minimal default workflow
    return (
        "WF_GENERAL",
        DEFAULT_STEPS,
        "AI service unavailable. Using default approval workflow.",
        None,
    )
