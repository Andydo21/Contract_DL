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

    from dotenv import load_dotenv
    from django.conf import settings
    env_file = getattr(settings, 'BASE_DIR').parent / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)

    kaggle_url = os.environ.get("KAGGLE_AI_URL", "").rstrip("/")
    if not kaggle_url:
        print("[recommend_workflow] KAGGLE_AI_URL is not configured in environment.", flush=True)
        return (
            "WF_GENERAL",
            DEFAULT_STEPS,
            "AI service unavailable (KAGGLE_AI_URL not configured). Using default approval workflow.",
            None,
        )

    endpoint = f"{kaggle_url}/api/v1/recommend_workflow"
    try:
        from shared.jwt_middleware import get_system_auth_header
        import json
        req_payload = {
            "contract_text": clean_text[:300] + "..." if len(clean_text) > 300 else clean_text,
            "clause_types": signals,
            "contract_type": declared_type,
        }
        try:
            print(f"[recommend_workflow] Sending request directly to Kaggle -> {endpoint}", flush=True)
            print(f"--- KAGGLE WORKFLOW RECOMMENDATION REQUEST PAYLOAD ---\n{json.dumps(req_payload, ensure_ascii=False, indent=2)}", flush=True)
        except Exception:
            try:
                print(f"--- KAGGLE WORKFLOW RECOMMENDATION REQUEST PAYLOAD ---\n{json.dumps(req_payload, indent=2)}", flush=True)
            except Exception:
                pass

        resp = requests.post(
            endpoint,
            json={
                "contract_text": clean_text,
                "clause_types": signals,
                "contract_type": declared_type,
            },
            headers=get_system_auth_header(),
            timeout=300,  # Increased to 300s (5 mins) to allow full AI inference completion
        )
        print(f"[recommend_workflow] Response status code: {resp.status_code}", flush=True)
        if resp.status_code == 200:
            data = resp.json()
            try:
                print(f"--- KAGGLE WORKFLOW RECOMMENDATION RESPONSE PAYLOAD ---\n{json.dumps(data, ensure_ascii=False, indent=2)}", flush=True)
            except Exception:
                try:
                    print(f"--- KAGGLE WORKFLOW RECOMMENDATION RESPONSE PAYLOAD ---\n{json.dumps(data, indent=2)}", flush=True)
                except Exception:
                    pass
            workflow_type = data.get("workflow_type", "WF_GENERAL")
            steps = data.get("steps", [])
            reasons = data.get("reasons", "")
            workflow_name = data.get("workflow_name")
            return workflow_type, steps, reasons, workflow_name
        else:
            try:
                print(f"[recommend_workflow] Kaggle returned non-200 status code: {resp.status_code} - {resp.text}", flush=True)
            except Exception:
                pass
    except Exception as e:
        print(f"[recommend_workflow] Error calling Kaggle endpoint {endpoint}: {e}", flush=True)

    # Fallback: AI unreachable — return minimal default workflow
    return (
        "WF_GENERAL",
        DEFAULT_STEPS,
        "AI service unavailable. Using default approval workflow.",
        None,
    )
