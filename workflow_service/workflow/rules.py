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
    Dynamically extracts clause keywords and generates a custom, highly specific workflow
    when external AI inference is offline.
    """
    c_text = (contract_text or "").lower()
    c_type = (contract_type or "").strip().upper()
    
    raw_steps = []
    
    # 1. Technical / SLA check
    if any(k in c_text for k in ['sla', 'kỹ thuật', 'phần mềm', 'hệ thống', 'bảo trì', 'cloud', 'server', 'dịch vụ']):
        raw_steps.append({
            "step_name": "Thẩm định Tiêu chuẩn Kỹ thuật, Hạ tầng Server & Cam kết SLA",
            "role_id": 7,
            "description": "Rà soát cam kết thời gian hoạt động (uptime), tiêu chuẩn hạ tầng và mốc hoàn thành bàn giao phần mềm."
        })

    # 2. Security & Data privacy check
    if any(k in c_text for k in ['bảo mật', 'security', 'iso 27001', 'dữ liệu', 'privacy', 'nda', 'bí mật']):
        raw_steps.append({
            "step_name": "Đánh giá Trách nhiệm Bảo mật Dữ liệu & An toàn Thông tin ISO 27001",
            "role_id": 8,
            "description": "Kiểm tra thỏa thuận bảo vệ dữ liệu cá nhân, chống rò rỉ bí mật kinh doanh và an toàn hệ thống."
        })

    # 3. Finance & Pricing check
    if any(k in c_text for k in ['giá', 'thanh toán', 'đặt cọc', 'ngân sách', 'chi phí', 'vnd', 'usd', 'thuế', 'phí']):
        raw_steps.append({
            "step_name": "Thẩm định Đơn giá Hợp đồng, Tiến độ Thanh toán & Tiền Đặt cọc",
            "role_id": 6,
            "description": "Xác nhận lịch giải ngân theo từng giai đoạn, điều khoản đặt cọc và khả năng cân đối dòng tiền."
        })

    # 4. Legal / Penalties / Termination check
    raw_steps.append({
        "step_name": "Rà soát Pháp lý Điều khoản Phạt Vi phạm, Bồi thường & Chấm dứt",
        "role_id": 4,
        "description": "Đánh giá tính hợp pháp của các chế tài xử lý vi phạm, mức phạt tối đa và quyền đơn phương chấm dứt."
    })

    final_steps = ensure_mandatory_anchor_steps(raw_steps)

    wf_type = c_type if c_type.startswith("WF_") else (f"WF_{c_type}" if c_type else "WF_DYNAMIC")
    label = wf_type.replace("WF_", "").title()
    reason = f"Quy trình tự động sinh với các bước neo bắt buộc và từ khóa hợp đồng ('{label}')."
    wf_name = f"Smart Approval Workflow – {label}"
    
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





