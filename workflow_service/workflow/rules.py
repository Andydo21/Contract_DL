import re
import unicodedata

TITLE_WINDOW_CHARS = 500

EXECUTIVE_PATTERN = re.compile(
    r"\b(chief executive officer|chief financial officer|chief operating officer|"
    r"chief technology officer|president and ceo|executive employment agreement|"
    r"employment agreement.{0,80}\b(chairman|president)\b|golden parachute|"
    r"giám đốc điều hành|ceo|giám đốc tài chính|cfo|giám đốc công nghệ|cto|chủ tịch|"
    r"ban điều hành|quản lý cấp cao|hợp đồng lao động cấp cao|hợp đồng lao động giám đốc)\b",
    re.IGNORECASE,
)
EXECUTIVE_CLAUSE_HINTS = {
    "change of control", "change-of-control", "severance", "golden parachute",
    "thay đổi quyền kiểm soát", "trợ cấp thôi việc", "bồi thường chấm dứt"
}

EMPLOYMENT_PATTERN = re.compile(
    r"\b(employment agreement|offer of employment|employment contract|at-will employment|"
    r"terms of employment|hợp đồng lao động|thỏa thuận lao động|hợp đồng thử việc|"
    r"hợp đồng cộng tác viên|tuyển dụng)\b",
    re.IGNORECASE,
)

NDA_PATTERN = re.compile(
    r"\b(non-disclosure agreement|nondisclosure agreement|non disclosure agreement|\bnda\b|"
    r"mutual confidentiality agreement|confidentiality agreement|thỏa thuận bảo mật|"
    r"hợp đồng bảo mật|cam kết bảo mật|thỏa thuận không tiết lộ|không tiết lộ thông tin)\b",
    re.IGNORECASE,
)

SERVICE_PATTERN = re.compile(
    r"\b(services agreement|service agreement|consulting agreement|master service agreement|\bmsa\b|"
    r"professional services agreement|independent contractor agreement|hợp đồng dịch vụ|"
    r"thỏa thuận dịch vụ|hợp đồng tư vấn|hợp đồng outsourcing|cung cấp dịch vụ)\b",
    re.IGNORECASE,
)

PROCUREMENT_PATTERN = re.compile(
    r"\b(procurement agreement|sourcing agreement|framework agreement|master purchase agreement|"
    r"purchasing agreement|hợp đồng mua sắm|hợp đồng cung ứng|hợp đồng khung|thỏa thuận mua sắm|"
    r"mua sắm thiết bị)\b",
    re.IGNORECASE,
)
PROCUREMENT_CLAUSE_HINTS = {
    "minimum commitment", "volume restriction", "price restriction", "most favored nation",
    "cam kết tối thiểu", "hạn chế số lượng", "hạn chế giá", "quốc gia ưu đãi nhất"
}

VENDOR_PATTERN = re.compile(
    r"\b(vendor agreement|supplier agreement|distributor agreement|reseller agreement|supply agreement|"
    r"hợp đồng nhà cung cấp|hợp đồng đại lý|hợp đồng phân phối|hợp đồng nhà phân phối|"
    r"thỏa thuận nhà cung cấp)\b",
    re.IGNORECASE,
)

PURCHASE_PATTERN = re.compile(
    r"\b(purchase agreement|asset purchase agreement|stock purchase agreement|sale and purchase agreement|"
    r"purchase order|hợp đồng mua bán|hợp đồng bán hàng|chuyển nhượng tài sản|mua bán thiết bị|"
    r"đơn đặt hàng)\b",
    re.IGNORECASE,
)


def clean_contract_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00a0", " ")
    text = "".join(ch for ch in text if ch in "\n\t" or ch >= " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def assign_workflow_id(contract_text: str, clause_types: list) -> str:
    """
    Deterministic rule engine to classify the contract into one of the 8 workflow types.
    """
    clean_text = clean_contract_text(contract_text)
    title_window = clean_text[:TITLE_WINDOW_CHARS]
    haystacks = (title_window, clean_text)
    clause_set = {c.lower() for c in clause_types if c}

    def matches(pattern):
        return any(pattern.search(h) for h in haystacks)

    # 1. WF_EXECUTIVE
    if matches(EXECUTIVE_PATTERN):
        return "WF_EXECUTIVE"
    if matches(EMPLOYMENT_PATTERN) and (clause_set & EXECUTIVE_CLAUSE_HINTS):
        return "WF_EXECUTIVE"

    # 2. WF_EMPLOYMENT
    if matches(EMPLOYMENT_PATTERN):
        return "WF_EMPLOYMENT"

    # 3. WF_NDA
    if matches(NDA_PATTERN):
        return "WF_NDA"

    # 4. WF_SERVICE
    if matches(SERVICE_PATTERN):
        return "WF_SERVICE"

    # 5. WF_PROCUREMENT
    if matches(PROCUREMENT_PATTERN):
        return "WF_PROCUREMENT"
    if (matches(PURCHASE_PATTERN) or matches(VENDOR_PATTERN)) and (clause_set & PROCUREMENT_CLAUSE_HINTS):
        return "WF_PROCUREMENT"

    # 6. WF_VENDOR
    if matches(VENDOR_PATTERN):
        return "WF_VENDOR"

    # 7. WF_PURCHASE
    if matches(PURCHASE_PATTERN):
        return "WF_PURCHASE"

    # 8. WF_GENERAL (default)
    return "WF_GENERAL"


# --- Canonical step library and ordering ---
STEP_LIBRARY = [
    "Contract Negotiation",
    "Legal Review",
    "Technical Review",
    "Security Review",
    "Compliance Review",
    "Finance Review",
    "Procurement Review",
    "Manager Approval",
    "Director Approval",
    "Executive Approval",
    "Contract Signing",
    "Document Archive",
]
STEP_ORDER = {step: i for i, step in enumerate(STEP_LIBRARY)}


def order_steps(step_set):
    return sorted(set(step_set), key=lambda s: STEP_ORDER.get(s, len(STEP_LIBRARY)))


# --- Signal detection helpers ---
def _text_has_any(text, keywords):
    t = text.lower()
    return any(kw in t for kw in keywords)


def _signals_have_any(signals, keywords):
    s = " | ".join(signals).lower()
    return any(kw in s for kw in keywords)


def is_nda(text, signals, declared_type):
    kws = ["non-disclosure", "nondisclosure", "confidentiality agreement", "nda",
           "thỏa thuận bảo mật", "cam kết bảo mật", "không tiết lộ"]
    return ("nda" in declared_type.lower() or "bảo mật" in declared_type.lower()) or _text_has_any(text, kws) or _signals_have_any(signals, ["confidential", "bảo mật"])


def is_software_or_technical(text, signals, declared_type):
    kws = ["software", "development agreement", "technical services", "saas",
           "source code", "api", "hosting", "system integration", "it services",
           "phần mềm", "phát triển phần mềm", "dịch vụ kỹ thuật", "tích hợp hệ thống", "công nghệ thông tin", "it"]
    return _text_has_any(text, kws) or _signals_have_any(signals, ["ip rights", "source code", "license", "sở hữu trí tuệ", "mã nguồn", "bản quyền"])


def has_financial_obligation(text, signals, declared_type):
    kws = ["payment", "fee", "invoice", "purchase price", "consideration",
           "compensation", "$", "usd", "cost", "expense", "vnd", "vnđ", "đồng", "thanh toán", "chi phí", "giá trị"]
    return _text_has_any(text, kws) or _signals_have_any(signals, ["payment", "revenue", "price", "thanh toán", "giá", "phí"])


def has_large_value_signal(text, signals, declared_type):
    money_matches = re.findall(r"(?:\$|usd|vnd|vnđ|đ|đồng)\s?([\d,\.]{7,})", text, re.IGNORECASE)
    big_number = False
    for m in money_matches:
        cleaned = m.replace(",", "").replace(".", "")
        if cleaned.isdigit():
            val = int(cleaned)
            if val >= 100000:
                big_number = True
                break
    kws = ["contract value", "total contract price", "aggregate amount", "giá trị hợp đồng", "tổng giá trị", "giá trị lớn"]
    return big_number or _text_has_any(text, kws)


def has_confidentiality(text, signals, declared_type):
    kws = ["confidential", "non-disclosure", "trade secret", "bảo mật", "bí mật kinh doanh", "không tiết lộ"]
    return _text_has_any(text, kws) or _signals_have_any(signals, ["confidential", "bảo mật"])


def has_ip_clause(text, signals, declared_type):
    kws = ["intellectual property", "copyright", "patent", "trademark", "proprietary rights",
           "sở hữu trí tuệ", "bản quyền", "quyền tác giả", "sáng chế", "nhãn hiệu", "quyền sở hữu"]
    return _text_has_any(text, kws) or _signals_have_any(signals, ["intellectual property", "ip", "sở hữu trí tuệ"])


def has_data_protection(text, signals, declared_type):
    kws = ["personal data", "data protection", "gdpr", "privacy", "data processing",
           "dữ liệu cá nhân", "bảo vệ dữ liệu", "quyền riêng tư", "bảo mật thông tin cá nhân"]
    return _text_has_any(text, kws) or _signals_have_any(signals, ["data protection", "privacy", "bảo vệ dữ liệu"])


def has_international_party(text, signals, declared_type):
    kws = ["foreign", "international", "cross-border", "export control",
           "governing law of", "united kingdom", "european union", "overseas",
           "nước ngoài", "quốc tế", "xuyên biên giới", "ngoại thương"]
    return _text_has_any(text, kws) or _signals_have_any(signals, ["international", "export", "quốc tế"])


def has_payment_terms(text, signals, declared_type):
    kws = ["net 30", "net 60", "payment terms", "installment", "milestone payment",
           "kỳ thanh toán", "tiến độ thanh toán", "đợt thanh toán", "điều khoản thanh toán"]
    return _text_has_any(text, kws) or _signals_have_any(signals, ["payment terms", "thanh toán"])


def has_termination_clause(text, signals, declared_type):
    kws = ["termination", "terminate this agreement", "right to terminate",
           "chấm dứt", "đơn phương chấm dứt", "hủy bỏ hợp đồng", "chấm dứt hợp đồng"]
    return _text_has_any(text, kws) or _signals_have_any(signals, ["termination", "chấm dứt"])


def has_negotiated_terms(text, signals, declared_type):
    kws = ["negotiate", "negotiation", "mutually agreed", "subject to further discussion",
           "thương lượng", "đàm phán", "thỏa thuận thêm", "thỏa thuận song phương"]
    return _text_has_any(text, kws)


WORKFLOW_RULES = [
    {
        "rule_name": "baseline_every_contract",
        "condition": lambda text, sig, dt: True,
        "generated_steps": ["Legal Review", "Contract Signing", "Document Archive"],
        "explanation": "Mọi hợp đồng đều phải qua đánh giá pháp lý trước khi ký và lưu trữ để phục vụ kiểm toán.",
    },
    {
        "rule_name": "nda_contract",
        "condition": is_nda,
        "generated_steps": ["Legal Review", "Manager Approval", "Contract Signing", "Document Archive"],
        "explanation": "Hợp đồng bảo mật NDA có rủi ro tài chính thấp nhưng đòi hỏi phê duyệt từ Quản lý trực tiếp.",
    },
    {
        "rule_name": "software_or_technical_contract",
        "condition": is_software_or_technical,
        "generated_steps": ["Technical Review", "Security Review", "Manager Approval"],
        "explanation": "Hợp đồng kỹ thuật/SaaS yêu cầu thẩm định tính khả thi kỹ thuật và bảo mật hệ thống.",
    },
    {
        "rule_name": "financial_obligation_present",
        "condition": has_financial_obligation,
        "generated_steps": ["Finance Review"],
        "explanation": "Hợp đồng phát sinh nghĩa vụ tài chính cần được phòng Tài chính kiểm tra ngân sách.",
    },
    {
        "rule_name": "large_value_contract",
        "condition": has_large_value_signal,
        "generated_steps": ["Finance Review", "Director Approval", "Executive Approval"],
        "explanation": "Hợp đồng giá trị lớn mang rủi ro tài chính cao, cần leo thang phê duyệt lên Giám đốc và Ban điều hành.",
    },
    {
        "rule_name": "confidentiality_clause",
        "condition": has_confidentiality,
        "generated_steps": ["Legal Review"],
        "explanation": "Điều khoản bảo mật phát sinh tăng nghĩa vụ pháp lý của các bên.",
    },
    {
        "rule_name": "intellectual_property_clause",
        "condition": has_ip_clause,
        "generated_steps": ["Legal Review", "Technical Review"],
        "explanation": "Liên quan đến chuyển giao/cấp phép SHTT cần rà soát pháp lý kỹ lưỡng và thẩm định kỹ thuật.",
    },
    {
        "rule_name": "data_protection_clause",
        "condition": has_data_protection,
        "generated_steps": ["Compliance Review", "Security Review"],
        "explanation": "Xử lý dữ liệu cá nhân kích hoạt các nghĩa vụ tuân thủ và bảo mật thông tin.",
    },
    {
        "rule_name": "international_party",
        "condition": has_international_party,
        "generated_steps": ["Compliance Review", "Executive Approval"],
        "explanation": "Hợp đồng có yếu tố nước ngoài tiềm ẩn rủi ro về quyền tài phán và luật áp dụng.",
    },
    {
        "rule_name": "payment_terms_specified",
        "condition": has_payment_terms,
        "generated_steps": ["Finance Review", "Procurement Review"],
        "explanation": "Kế hoạch thanh toán cụ thể cần kiểm tra dòng tiền và chính sách mua sắm.",
    },
    {
        "rule_name": "termination_clause_present",
        "condition": has_termination_clause,
        "generated_steps": ["Legal Review"],
        "explanation": "Điều khoản chấm dứt hợp đồng quyết định cơ chế rút lui an toàn của doanh nghiệp.",
    },
    {
        "rule_name": "negotiated_terms_present",
        "condition": has_negotiated_terms,
        "generated_steps": ["Contract Negotiation"],
        "explanation": "Hợp đồng có tín hiệu chưa hoàn thiện cần trải qua bước thương lượng trước khi phê duyệt chính thức.",
    },
]


import os
import requests

def recommend_workflow(text: str, clause_types: list, contract_type: str):
    """
    Exposes recommendation to create endpoint.
    Attempts to call external AI recommendation service (local or Kaggle Ngrok).
    Falls back to deterministic rule-based logic.
    Returns: (workflow_type, steps_list, reasons_str, ai_workflow_name)
    """
    clean_text = clean_contract_text(text)
    signals = [clean_contract_text(c) for c in clause_types if c]
    declared_type = clean_contract_text(contract_type)

    # 1. Attempt to call external AI Service
    ai_service_url = os.environ.get("AI_SERVICE_URL")
    urls_to_try = []
    if ai_service_url:
        urls_to_try.append(ai_service_url.rstrip("/"))
    urls_to_try.extend(["http://ai-service:8000", "http://localhost:8001"])

    kaggle_ai_url = os.environ.get("KAGGLE_AI_URL")
    if kaggle_ai_url:
        urls_to_try.insert(0, kaggle_ai_url.rstrip("/"))

    ai_success = False
    ai_data = {}
    
    seen = set()
    unique_urls = [x for x in urls_to_try if not (x in seen or seen.add(x))]

    for url in unique_urls:
        endpoint = f"{url}/api/v1/recommend_workflow"
        try:
            resp = requests.post(
                endpoint,
                json={
                    "contract_text": clean_text,
                    "clause_types": signals,
                    "contract_type": declared_type
                },
                timeout=60  # Kaggle model may take time on first inference
            )
            if resp.status_code == 200:
                ai_data = resp.json()
                ai_success = True
                break
        except Exception:
            continue

    if ai_success:
        workflow_type = ai_data.get("workflow_type", "WF_GENERAL")
        recommended_steps = ai_data.get("steps", [])
        reasons = ai_data.get("reasons", "")
        ai_workflow_name = ai_data.get("workflow_name")
        return workflow_type, recommended_steps, reasons, ai_workflow_name

    # 2. Rule-based Fallback
    workflow_type = assign_workflow_id(clean_text, signals)

    fired_rules = []
    steps = set()
    for rule in WORKFLOW_RULES:
        if rule["condition"](clean_text, signals, declared_type):
            fired_rules.append(rule["rule_name"])
            steps.update(rule["generated_steps"])

    ordered = order_steps(steps)

    reasons_list = []
    for rname in fired_rules:
        rule = next(r for r in WORKFLOW_RULES if r["rule_name"] == rname)
        reasons_list.append(f"- [{rule['rule_name']}] {rule['explanation']}")
    reasons = "\n".join(reasons_list)

    return workflow_type, ordered, reasons, None
