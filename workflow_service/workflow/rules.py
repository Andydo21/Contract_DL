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


# ==============================================================================
# ROLE & CAPABILITY KNOWLEDGE CATALOG FOR DYNAMIC WORKFLOW GENERATION
# ==============================================================================
ROLE_KNOWLEDGE_BASE = {
    "Pháp lý Rà soát Điều khoản Hợp đồng": {"role_id": 4,  "desc": "Kế hoạch kiểm tra tính pháp lý, rủi ro điều khoản bồi thường và chấm dứt."},
    "Tài chính Thẩm định Đơn giá & Ngân sách": {"role_id": 6,  "desc": "Thẩm định ngân sách chi trả, lịch thanh toán và chi phí phát sinh."},
    "Kỹ thuật Thẩm định Giải pháp & SLA": {"role_id": 7,  "desc": "Đánh giá tiêu chuẩn kỹ thuật, mốc bàn giao và cam kết chất lượng dịch vụ."},
    "Đánh giá An toàn Thông tin & Bảo mật": {"role_id": 8,  "desc": "Kiểm tra quy định bảo mật dữ liệu cá nhân, hạ tầng và tiêu chuẩn an ninh mạng."},
    "Rà soát Tuân thủ Quản trị Doanh nghiệp": {"role_id": 9,  "desc": "Kiểm tra sự tuân thủ quy chế nội bộ, chống xung đột lợi ích."},
    "Mua sắm Thẩm định Nhà cung cấp & Báo giá": {"role_id": 10, "desc": "Đánh giá báo giá cạnh tranh và năng lực thực hiện của bên đối tác."},
    "Quản lý Phê duyệt Chủ trương Triển khai": {"role_id": 5,  "desc": "Cấp quản lý trực tiếp duyệt phương án và chủ trương thực hiện."},
    "Giám đốc Phê duyệt Chiến lược & Ngân sách": {"role_id": 11, "desc": "Giám đốc phê duyệt hợp đồng chiến lược và ngân sách lớn."},
    "Ký kết Hợp đồng": {"role_id": 4,  "desc": "Đại diện pháp luật ký kết hợp đồng chính thức."},
    "Lưu trữ Hồ sơ & Bàn giao": {"role_id": 4,  "desc": "Lưu trữ bản cứng hợp đồng và hồ sơ liên quan vào hệ thống."},
}


def ensure_mandatory_anchor_steps(steps: list) -> list:
    """
    Guarantees mandatory corporate governance anchors:
    - Initial Step: Mandatory Legal & Draft Intake Review
    - Middle Steps: Dynamic AI-generated clause verification tasks (SLA, Security, Deposit, IP, etc.)
    - Pre-Final Step: Mandatory Manager / Executive Approval
    - Final 2 Steps: Mandatory Official Contract Signing & Document Archiving
    """
    if not steps:
        steps = []

    normalized_steps = []
    for st in steps:
        if isinstance(st, dict):
            normalized_steps.append(st)
        elif hasattr(st, "step_name"):
            normalized_steps.append({
                "step_name": st.step_name,
                "role_id": getattr(st, "role_id", 4),
                "description": getattr(st, "description", "")
            })

    # 1. Ensure Step 1: Initial Legal & Draft Review exists
    first_name = (normalized_steps[0].get("step_name") if normalized_steps else "").lower()
    if not any(k in first_name for k in ["sơ bộ", "đầu tiên", "tổng quan", "tiếp nhận", "dự thảo", "đăng ký", "kiểm tra ban đầu"]):
        normalized_steps.insert(0, {
            "step_name": "Rà soát & Tiếp nhận Dự thảo Hợp đồng",
            "role_id": 4,
            "description": "Kiểm tra tính đầy đủ của hồ sơ dự thảo, tư cách pháp nhân các bên và hình thức hợp đồng."
        })

    # Filter out any existing trailing signing/archive steps to re-append clean mandatory final steps
    middle_steps = []
    for st in normalized_steps:
        name_lower = st.get("step_name", "").lower()
        if not any(k in name_lower for k in ["ký kết", "signing", "lưu trữ", "archive"]):
            middle_steps.append(st)

    # 2. Ensure mandatory Manager / Executive approval exists before signing
    has_approval_step = any(
        st.get("role_id") in (5, 11) or any(k in st.get("step_name", "").lower() for k in ["phê duyệt", "chủ trương", "quản lý", "giám đốc", "ban điều hành"])
        for st in middle_steps
    )
    if not has_approval_step:
        middle_steps.append({
            "step_name": "Phê duyệt Chủ trương & Phương án Thực hiện Cấp Quản lý",
            "role_id": 5,
            "description": "Cấp quản lý trực tiếp xét duyệt phương án triển khai, chi phí và định hướng hợp đồng."
        })

    # 3. Append mandatory final signing & archive steps
    middle_steps.append({
        "step_name": "Thực hiện Ký kết Hợp đồng Chính thức",
        "role_id": 4,
        "description": "Đại diện có thẩm quyền của các bên thực hiện ký kết hợp đồng bằng chữ ký số."
    })
    middle_steps.append({
        "step_name": "Bàn giao Bản cứng & Lưu trữ Kho Hồ sơ Hợp đồng",
        "role_id": 4,
        "description": "Lưu trữ bản hợp đồng chính thức và các tài liệu bàn giao liên quan vào hệ thống quản lý."
    })

    # Re-index step_order sequentially
    for idx, st in enumerate(middle_steps, start=1):
        st["step_order"] = idx

    return middle_steps


def build_dynamic_fallback_workflow(contract_text: str = "", contract_type: str = "") -> tuple:
    """
    Standard default workflow when non-AI mode is selected or AI service is offline.
    Generates a clean, concise 4-step corporate approval workflow.
    """
    c_type = (contract_type or "").strip().upper()
    wf_type = c_type if c_type.startswith("WF_") else (f"WF_{c_type}" if c_type else "WF_STANDARD")
    label = wf_type.replace("WF_", "").title()
    wf_name = f"Quy trình Phê duyệt Mặc định – {label}" if label and label != "Standard" else "Quy trình Phê duyệt Mặc định"
    reason = "Quy trình phê duyệt tiêu chuẩn mặc định (4 bước cơ bản)."

    final_steps = [
        {
            "step_order": 1,
            "step_name": "Rà soát & Tiếp nhận Dự thảo Hợp đồng",
            "role_id": 4,
            "description": "Kiểm tra tính đầy đủ của hồ sơ dự thảo, tư cách pháp nhân các bên và hình thức hợp đồng."
        },
        {
            "step_order": 2,
            "step_name": "Phê duyệt Chủ trương Cấp Quản lý",
            "role_id": 5,
            "description": "Cấp quản lý trực tiếp xét duyệt phương án triển khai, chi phí và định hướng hợp đồng."
        },
        {
            "step_order": 3,
            "step_name": "Thực hiện Ký kết Hợp đồng Chính thức",
            "role_id": 4,
            "description": "Đại diện có thẩm quyền của các bên thực hiện ký kết hợp đồng bằng chữ ký số."
        },
        {
            "step_order": 4,
            "step_name": "Bàn giao & Lưu trữ Kho Hồ sơ Hợp đồng",
            "role_id": 4,
            "description": "Lưu trữ bản hợp đồng chính thức và các tài liệu bàn giao liên quan vào hệ thống quản lý."
        }
    ]
    
    return wf_type, final_steps, reason, wf_name


def recommend_workflow(text: str, clause_types: list, contract_type: str):
    """
    Delegates 100% of workflow step generation & sequencing to the fine-tuned LLM AI service.
    Ensures mandatory compliance anchor steps (Initial intake, Manager approval, Signing, Archive).
    Returns: (workflow_type, steps_list, reasons_str, ai_workflow_name)
    """
    clean_text = clean_contract_text(text)
    signals = [clean_contract_text(c) for c in (clause_types or []) if c]
    declared_type = clean_contract_text(contract_type)

    from dotenv import load_dotenv
    from django.conf import settings
    env_file = getattr(settings, 'BASE_DIR').parent / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)

    kaggle_url = os.environ.get("KAGGLE_AI_URL", "").rstrip("/")
    if kaggle_url:
        endpoint = f"{kaggle_url}/api/v1/recommend_workflow"
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
                timeout=300,
            )
            if resp.status_code == 200:
                data = resp.json()
                workflow_type = data.get("workflow_type", "WF_DYNAMIC")
                steps = data.get("steps", [])
                reasons = data.get("reasons", "")
                workflow_name = data.get("workflow_name")

                if steps and len(steps) >= 1:
                    final_steps = ensure_mandatory_anchor_steps(steps)
                    return workflow_type, final_steps, reasons, workflow_name
        except Exception as e:
            print(f"[recommend_workflow] Error calling AI service {endpoint}: {e}", flush=True)

    return build_dynamic_fallback_workflow(clean_text, declared_type)





