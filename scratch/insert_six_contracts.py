import os
import sys
import django
from django.utils import timezone
from decimal import Decimal
import uuid
import psycopg2

# Set up Django environment
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from contracts.models import Contract, ContractVersion, ContractFile, Company, RiskRule, AIAnalysis, RiskFinding, ContractParty, Tag
from ai_extract.models import Clause, ExtractedEntity
from contracts.crypto_utils import encrypt_pdf
from django.conf import settings

def create_six_contracts():
    print("=== Start Seeding 6 Diverse Contracts ===")
    
    # 1. Fetch Company
    company = Company.objects.filter(company_name='FPT Software JSC').first()
    if not company:
        company = Company.objects.create(company_name='FPT Software JSC', tax_code='0101248141')

    # Fetch User
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.filter(username='Doan2108').first()

    # Define Tags
    tag_ai, _ = Tag.objects.get_or_create(tag_name='Artificial-Intelligence')
    tag_cloud, _ = Tag.objects.get_or_create(tag_name='Cloud-Services')
    tag_security, _ = Tag.objects.get_or_create(tag_name='Cybersecurity')
    tag_maintenance, _ = Tag.objects.get_or_create(tag_name='Maintenance')
    tag_license, _ = Tag.objects.get_or_create(tag_name='License')
    tag_event, _ = Tag.objects.get_or_create(tag_name='Event')

    # Connect to blockchain database
    try:
        conn = psycopg2.connect(
            dbname='blockchain_db',
            user=os.environ.get("DB_USER"),
            password=os.environ.get("DB_PASSWORD"),
            host=os.environ.get("DB_HOST"),
            port=os.environ.get("DB_PORT"),
            sslmode=os.environ.get("DB_SSLMODE", "require")
        )
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM blockchain_blockchainnetwork LIMIT 1")
        network_id = cursor.fetchone()[0]
        cursor.execute("SELECT id FROM blockchain_smartcontract LIMIT 1")
        smart_contract_id = cursor.fetchone()[0]
    except Exception as e:
        print(f"Warning: Failed to connect to blockchain db: {e}")
        conn = None

    contracts_data = [
        {
            "code": "AI-COLLAB-2026",
            "title": "Hợp đồng Hợp tác Nghiên cứu và Phát triển Mô hình AI sinh thành (FPT & VinAI)",
            "type": "Collaboration",
            "value": Decimal("120000.00"),
            "tags": [tag_ai],
            "parties": [
                {"name": "Công ty Cổ phần FPT Software (FPT Software JSC)", "tax_code": "0101248141", "email": "ai-partner@fpt-software.com", "phone": "02437689048", "type": "PARTY_A"},
                {"name": "Công ty Cổ phần Nghiên cứu và Ứng dụng Trí tuệ Nhân tạo VinAI (VinAI)", "tax_code": "0108849503", "email": "collab@vinai.io", "phone": "02439749999", "type": "PARTY_B"}
            ],
            "text": """CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc
---
HỢP ĐỒNG HỢP TÁC NGHIÊN CỨU PHÁT TRIỂN CÔNG NGHỆ AI

Hôm nay, ngày 18 tháng 07 năm 2026, tại Hà Nội:
Bên A: Công ty Cổ phần FPT Software (FPT Software JSC)
Bên B: Công ty Cổ phần Nghiên cứu và Ứng dụng Trí tuệ Nhân tạo VinAI (VinAI)

Điều 1: Nội dung hợp tác
Hai bên cùng đóng góp nhân sự và hạ tầng tính toán GPU để cùng nghiên cứu và phát triển mô hình ngôn ngữ lớn (LLM) phục vụ phân tích ngôn ngữ pháp lý tiếng Việt.

Điều 2: Đóng góp tài chính và phân chia chi phí
Tổng giá trị ngân sách dự án là 120,000 USD. Bên A đóng góp 60% chi phí. Bên B đóng góp 40%. Tất cả các khoản chi tiêu phải được ban điều hành chung phê duyệt trước khi thực hiện.

Điều 3: Quyền sở hữu trí tuệ và Sử dụng thương mại
Mọi quyền sở hữu trí tuệ đối với mô hình AI nền tảng được tạo ra sẽ thuộc về sở hữu chung của hai bên. Tuy nhiên, Bên B có quyền sử dụng độc quyền mô hình này trong lĩnh vực y tế, trong khi Bên A có quyền sử dụng độc quyền mô hình này trong lĩnh vực tài chính ngân hàng. Mọi hoạt động cấp phép thương mại cho bên thứ ba phải có sự đồng ý bằng văn bản của cả hai bên.

Điều 4: Giới hạn trách nhiệm pháp lý
Bên B cam kết các kết quả thuật toán không vi phạm bản quyền thuật toán quốc tế. Trường hợp xảy ra tranh chấp từ bên thứ ba, bên vi phạm sẽ chịu toàn bộ trách nhiệm bồi thường vô hạn cho bên bị ảnh hưởng.

Điều 5: Luật áp dụng
Hợp đồng tuân thủ pháp luật Việt Nam. Tranh chấp giải quyết tại VIAC.""",
            "clauses": [
                {"title": "Điều 3: Quyền sở hữu trí tuệ và Sử dụng thương mại", "content": "Mọi quyền sở hữu trí tuệ đối với mô hình AI nền tảng được tạo ra sẽ thuộc về sở hữu chung của hai bên. Tuy nhiên, Bên B có quyền sử dụng độc quyền mô hình này trong lĩnh vực y tế, trong khi Bên A có quyền sử dụng độc quyền mô hình này trong lĩnh vực tài chính ngân hàng. Mọi hoạt động cấp phép thương mại cho bên thứ ba phải có sự đồng ý bằng văn bản của cả hai bên.", "type": "IP"},
                {"title": "Điều 4: Giới hạn trách nhiệm pháp lý", "content": "Bên B cam kết các kết quả thuật toán không vi phạm bản quyền thuật toán quốc tế. Trường hợp xảy ra tranh chấp từ bên thứ ba, bên vi phạm sẽ chịu toàn bộ trách nhiệm bồi thường vô hạn cho bên bị ảnh hưởng.", "type": "LIABILITY"}
            ],
            "entities": [
                {"type": "CONTRACT_VALUE", "value": "120,000 USD", "norm": "120000"},
                {"type": "COMPANY_NAME", "value": "VinAI", "norm": "VINAI"}
            ],
            "analysis": {
                "score": Decimal("65.00"),
                "level": "MEDIUM",
                "summary": "Hợp đồng có rủi ro về trách nhiệm bồi thường vô hạn (uncapped liability) liên quan đến tranh chấp bản quyền thuật toán từ bên thứ ba tại Điều 4."
            },
            "findings": [
                {
                    "rule_name": "Limitation of Liability Risk",
                    "clause_index": 1,
                    "score": Decimal("75.00"),
                    "level": "HIGH",
                    "explanation": "Điều khoản bồi thường vô hạn cho các tranh chấp sở hữu trí tuệ tạo ra gánh nặng tài chính khôn lường cho bên thực hiện.",
                    "recommendation": "Đề xuất quy định mức trần bồi thường thiệt hại tối đa không quá 100% giá trị hợp đồng.",
                    "party": "Bên B (VinAI)"
                }
            ]
        },
        {
            "code": "CLOUD-AWS-2026",
            "title": "Hợp đồng Cung cấp Dịch vụ Điện toán Đám mây AWS (FPT & Amazon)",
            "type": "Cloud Services",
            "value": Decimal("450000.00"),
            "tags": [tag_cloud],
            "parties": [
                {"name": "Công ty Cổ phần FPT Software (FPT Software JSC)", "tax_code": "0101248141", "email": "cloud-ops@fpt-software.com", "phone": "02437689048", "type": "CLIENT"},
                {"name": "Amazon Web Services Vietnam Co., Ltd (AWS)", "tax_code": "0316889240", "email": "billing@aws.amazon.com", "phone": "02839113300", "type": "PROVIDER"}
            ],
            "text": """CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc
---
HỢP ĐỒNG CUNG CẤP DỊCH VỤ ĐIỆN TOÁN ĐÁM MÂY

Hôm nay, ngày 18 tháng 07 năm 2026, tại TP. Hồ Chí Minh:
Bên A: Công ty Cổ phần FPT Software (FPT Software JSC)
Bên B: Amazon Web Services Vietnam Co., Ltd (AWS)

Điều 1: Dịch vụ cung cấp
Bên B cung cấp dịch vụ hạ tầng điện toán đám mây (EC2, S3, RDS, EKS) trên nền tảng AWS cho Bên A phục vụ chạy ứng dụng doanh nghiệp.

Điều 2: Phí dịch vụ và Điều chỉnh giá
Tổng chi phí sử dụng dịch vụ dự kiến hàng năm là 450,000 USD thanh toán hàng tháng dựa trên lượng tài nguyên tiêu thụ thực tế. Bên B có quyền đơn phương thay đổi biểu phí dịch vụ bất kỳ lúc nào bằng cách thông báo trước 30 ngày cho Bên A.

Điều 3: Cam kết mức độ dịch vụ (SLA)
Bên B cam kết tỷ lệ khả dụng hàng tháng của dịch vụ đạt tối thiểu 99.99%. Trường hợp thời gian gián đoạn vượt quá mức cam kết, biện pháp khắc phục duy nhất của Bên B là hoàn trả khoản tín dụng dịch vụ (Service Credits) tương đương 10% phí tháng đó. Bên B không bồi thường bất kỳ thiệt hại trực tiếp hay gián tiếp nào khác.

Điều 4: Giải quyết tranh chấp
Hợp đồng áp dụng luật pháp Singapore. Mọi tranh chấp được giải quyết tại Trung tâm Trọng tài Quốc tế Singapore (SIAC).""",
            "clauses": [
                {"title": "Điều 2: Phí dịch vụ và Điều chỉnh giá", "content": "Bên B có quyền đơn phương thay đổi biểu phí dịch vụ bất kỳ lúc nào bằng cách thông báo trước 30 ngày cho Bên A.", "type": "PRICE"},
                {"title": "Điều 3: Cam kết mức độ dịch vụ (SLA)", "content": "Bên B cam kết tỷ lệ khả dụng hàng tháng của dịch vụ đạt tối thiểu 99.99%. Trường hợp thời gian gián đoạn vượt quá mức cam kết, biện pháp khắc phục duy nhất của Bên B là hoàn trả khoản tín dụng dịch vụ (Service Credits) tương đương 10% phí tháng đó. Bên B không bồi thường bất kỳ thiệt hại trực tiếp hay gián tiếp nào khác.", "type": "SLA"}
            ],
            "entities": [
                {"type": "CONTRACT_VALUE", "value": "450,000 USD", "norm": "450000"},
                {"type": "COMPANY_NAME", "value": "Amazon Web Services", "norm": "AWS"}
            ],
            "analysis": {
                "score": Decimal("72.00"),
                "level": "HIGH",
                "summary": "Hợp đồng có rủi ro về việc Nhà cung cấp được quyền đơn phương điều chỉnh giá dịch vụ (Điều 2) và giới hạn trách nhiệm bồi thường SLA quá hẹp (chỉ hoàn trả tín dụng dịch vụ)."
            },
            "findings": [
                {
                    "rule_name": "Payment Risk",
                    "clause_index": 0,
                    "score": Decimal("70.00"),
                    "level": "MEDIUM",
                    "explanation": "AWS có quyền đơn phương tăng giá chỉ sau 30 ngày báo trước, gây khó khăn cho Bên A trong việc lập dự toán ngân sách.",
                    "recommendation": "Đề xuất đàm phán mức trần tăng giá tối đa không quá 5% mỗi năm hoặc cố định biểu phí dịch vụ trong 12 tháng.",
                    "party": "Bên A (FPT Software JSC)"
                },
                {
                    "rule_name": "Limitation of Liability Risk",
                    "clause_index": 1,
                    "score": Decimal("80.00"),
                    "level": "HIGH",
                    "explanation": "Quy định loại trừ mọi bồi thường thiệt hại trực tiếp/gián tiếp ngoài tín dụng dịch vụ 10% làm triệt tiêu trách nhiệm đền bù khi hệ thống bị sập gây thiệt hại lớn cho Bên A.",
                    "recommendation": "Yêu cầu bổ sung giới hạn trách nhiệm đền bù thiệt hại thực tế tối thiểu tương đương 6 tháng phí dịch vụ trung bình.",
                    "party": "Bên A (FPT Software JSC)"
                }
            ]
        },
        {
            "code": "SEC-STAFF-2026",
            "title": "Hợp đồng Cung cấp Nhân sự Bảo mật Thông tin và Giám sát SOC",
            "type": "Security Services",
            "value": Decimal("95000.00"),
            "tags": [tag_security],
            "parties": [
                {"name": "Công ty Cổ phần FPT Software (FPT Software JSC)", "tax_code": "0101248141", "email": "soc-sec@fpt-software.com", "phone": "02437689048", "type": "CLIENT"},
                {"name": "Công ty Cổ phần An ninh mạng CyRadar (CyRadar)", "tax_code": "0106849925", "email": "info@cyradar.com", "phone": "02466883311", "type": "PROVIDER"}
            ],
            "text": """CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc
---
HỢP ĐỒNG CUNG CẤP NHÂN LỰC AN NINH THÔNG TIN

Hôm nay, ngày 18 tháng 07 năm 2026, tại Hà Nội:
Bên A: Công ty Cổ phần FPT Software (FPT Software JSC)
Bên B: Công ty Cổ phần An ninh mạng CyRadar (CyRadar)

Điều 1: Dịch vụ cung cấp
Bên B cử 03 chuyên gia bảo mật cao cấp làm việc trực ca 24/7 tại trung tâm SOC của bên A để giám sát an ninh mạng và ứng phó sự cố.

Điều 2: Bảo mật thông tin khách hàng và hệ thống
Bên B cam kết toàn bộ nhân sự tuân thủ nghiêm ngặt quy trình bảo mật của Bên A. Nếu nhân sự của Bên B làm rò rỉ dữ liệu hoặc mã nguồn của Bên A, Bên B sẽ bị phạt vi phạm 100% giá trị hợp đồng và bồi thường toàn bộ thiệt hại phát sinh.

Điều 3: Cam kết không lôi kéo nhân sự (Non-solicitation)
Trong thời gian thực hiện hợp đồng và trong vòng 12 tháng kể từ ngày chấm dứt hợp đồng, Bên A không được tuyển dụng trực tiếp hoặc gián tiếp các chuyên gia của Bên B. Nếu Bên A vi phạm điều khoản này, Bên A sẽ phải thanh toán cho Bên B khoản tiền phạt tương đương 12 tháng lương của nhân sự đó.""",
            "clauses": [
                {"title": "Điều 2: Bảo mật thông tin khách hàng và hệ thống", "content": "Nếu nhân sự của Bên B làm rò rỉ dữ liệu hoặc mã nguồn của Bên A, Bên B sẽ bị phạt vi phạm 100% giá trị hợp đồng và bồi thường toàn bộ thiệt hại phát sinh.", "type": "CONFIDENTIALITY"},
                {"title": "Điều 3: Cam kết không lôi kéo nhân sự (Non-solicitation)", "content": "Trong thời gian thực hiện hợp đồng và trong vòng 12 tháng kể từ ngày chấm dứt hợp đồng, Bên A không được tuyển dụng trực tiếp hoặc gián tiếp các chuyên gia của Bên B. Nếu Bên A vi phạm điều khoản này, Bên A sẽ phải thanh toán cho Bên B khoản tiền phạt tương đương 12 tháng lương của nhân sự đó.", "type": "NON_COMPETE"}
            ],
            "entities": [
                {"type": "CONTRACT_VALUE", "value": "95,000 USD", "norm": "95000"},
                {"type": "COMPANY_NAME", "value": "CyRadar", "norm": "CYRADAR"}
            ],
            "analysis": {
                "score": Decimal("40.00"),
                "level": "LOW",
                "summary": "Hợp đồng có điều khoản cam kết không lôi kéo nhân sự tiêu chuẩn (Điều 3) và điều khoản bảo mật nghiêm ngặt (Điều 2) bảo vệ Bên A."
            },
            "findings": [
                {
                    "rule_name": "Confidentiality Requirement",
                    "clause_index": 0,
                    "score": Decimal("20.00"),
                    "level": "LOW",
                    "explanation": "Điều khoản bảo mật rất chặt chẽ, phạt 100% giá trị hợp đồng nếu rò rỉ thông tin là phù hợp để bảo vệ tài sản số của Bên A.",
                    "recommendation": "Giữ nguyên điều khoản này.",
                    "party": None
                }
            ]
        },
        {
            "code": "MAINT-BANK-2026",
            "title": "Hợp đồng Bảo trì và Hỗ trợ Kỹ thuật Phần mềm Core-Banking",
            "type": "Maintenance Agreement",
            "value": Decimal("60000.00"),
            "tags": [tag_maintenance],
            "parties": [
                {"name": "Ngân hàng TMCP Kỹ thương Việt Nam (Techcombank)", "tax_code": "0100230800", "email": "support@techcombank.com.vn", "phone": "1800588822", "type": "CLIENT"},
                {"name": "Công ty Cổ phần FPT Software (FPT Software JSC)", "tax_code": "0101248141", "email": "maintenance@fpt-software.com", "phone": "02437689048", "type": "PROVIDER"}
            ],
            "text": """CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc
---
HỢP ĐỒNG BẢO TRÌ HỆ THỐNG PHẦN MỀM

Hôm nay, ngày 18 tháng 07 năm 2026, tại Hà Nội:
Bên A: Ngân hàng TMCP Kỹ thương Việt Nam (Techcombank)
Bên B: Công ty Cổ phần FPT Software (FPT Software JSC)

Điều 1: Dịch vụ bảo trì
Bên B cung cấp dịch vụ bảo trì định kỳ, sửa lỗi phát sinh và cập nhật các tính năng nhỏ cho phần mềm Core-Banking của Bên A.

Điều 2: Thời gian phản hồi và Xử lý sự cố (SLA)
Bên B cam kết tiếp nhận sự cố mức độ Nghiêm trọng (Lỗi ngắt kết nối giao dịch) trong vòng 15 phút đầu tiên và khắc phục hoàn toàn lỗi trong vòng tối đa 02 giờ. Nếu quá thời hạn khắc phục 2 giờ, Bên B chịu phạt mức phạt cố định là $2,000 cho mỗi giờ lỗi kéo dài tiếp theo mà không có giới hạn trần phạt.

Điều 3: Giới hạn trách nhiệm bồi thường
Bên B bồi thường thiệt hại phát sinh trực tiếp từ lỗi bảo trì của mình nhưng giới hạn tối đa cho mọi bồi thường không vượt quá 100% giá trị hợp đồng năm hiện tại.""",
            "clauses": [
                {"title": "Điều 2: Thời gian phản hồi và Xử lý sự cố (SLA)", "content": "Bên B cam kết tiếp nhận sự cố mức độ Nghiêm trọng trong vòng 15 phút đầu tiên và khắc phục hoàn toàn lỗi trong vòng tối đa 02 giờ. Nếu quá thời hạn khắc phục 2 giờ, Bên B chịu phạt mức phạt cố định là $2,000 cho mỗi giờ lỗi kéo dài tiếp theo mà không có giới hạn trần phạt.", "type": "SLA"},
                {"title": "Điều 3: Giới hạn trách nhiệm bồi thường", "content": "Bên B bồi thường thiệt hại phát sinh trực tiếp từ lỗi bảo trì của mình nhưng giới hạn tối đa cho mọi bồi thường không vượt quá 100% giá trị hợp đồng năm hiện tại.", "type": "LIABILITY"}
            ],
            "entities": [
                {"type": "CONTRACT_VALUE", "value": "60,000 USD", "norm": "60000"},
                {"type": "COMPANY_NAME", "value": "Techcombank", "norm": "TECHCOMBANK"}
            ],
            "analysis": {
                "score": Decimal("58.00"),
                "level": "MEDIUM",
                "summary": "Hợp đồng bảo trì hệ thống ngân hàng có mức phạt SLA chậm trễ $2,000/giờ không giới hạn trần phạt, tạo nguy cơ chịu phạt vượt quá giá trị hợp đồng đối với FPT Software."
            },
            "findings": [
                {
                    "rule_name": "Phạt vi phạm & Bồi thường",
                    "clause_index": 0,
                    "score": Decimal("75.00"),
                    "level": "HIGH",
                    "explanation": "Mức phạt $2,000 mỗi giờ chậm trễ SLA không giới hạn trần phạt là rủi ro rất cao đối với nhà cung cấp dịch vụ, đặc biệt khi giá trị hợp đồng chỉ là $60,000.",
                    "recommendation": "Thêm điều khoản giới hạn tổng số tiền phạt vi phạm SLA trong cả năm tối đa không quá 8% tổng giá trị hợp đồng bảo trì thường niên.",
                    "party": "Bên B (FPT Software JSC)"
                }
            ]
        },
        {
            "code": "SAP-LIC-2026",
            "title": "Hợp đồng Cấp phép Bản quyền Phần mềm SAP S/4HANA ERP",
            "type": "Software License",
            "value": Decimal("300000.00"),
            "tags": [tag_license],
            "parties": [
                {"name": "Công ty Cổ phần FPT Software (FPT Software JSC)", "tax_code": "0101248141", "email": "sap-license@fpt-software.com", "phone": "02437689048", "type": "LICENSEE"},
                {"name": "Công ty TNHH SAP Việt Nam (SAP)", "tax_code": "0305719920", "email": "sales-vn@sap.com", "phone": "02838232900", "type": "LICENSOR"}
            ],
            "text": """CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc
---
HỢP ĐỒNG CẤP PHÉP SỬ DỤNG BẢN QUYỀN PHẦN MỀM ERP

Hôm nay, ngày 18 tháng 07 năm 2026, tại Hà Nội:
Bên A: Công ty Cổ phần FPT Software (FPT Software JSC)
Bên B: Công ty TNHH SAP Việt Nam (SAP)

Điều 1: Cấp phép bản quyền
Bên B cấp quyền sử dụng phần mềm quản trị doanh nghiệp SAP S/4HANA cho Bên A gồm 500 giấy phép người dùng (User Licenses). Quyền sử dụng là không độc quyền, không được chuyển nhượng.

Điều 2: Giá trị và Thanh toán
Tổng giá trị bản quyền phần mềm và năm đầu hỗ trợ là 300,000 USD. Thanh toán một lần trong vòng 30 ngày kể từ ngày cài đặt kích hoạt mã khóa (License Keys).

Điều 3: Quyền kiểm tra sử dụng phần mềm (Audit rights)
Bên B có quyền kiểm tra đột xuất phần mềm hệ thống của Bên A (thông báo trước 05 ngày làm việc) để xác thực số lượng người dùng thực tế không vượt quá số lượng 500 giấy phép được cấp. Nếu phát hiện số người dùng thực tế vượt quá, Bên A có trách nhiệm mua bổ sung giấy phép với đơn giá bằng 150% đơn giá chuẩn kèm theo mức phạt vi phạm sử dụng quá số lượng bằng 20% giá trị hợp đồng.""",
            "clauses": [
                {"title": "Điều 3: Quyền kiểm tra sử dụng phần mềm (Audit rights)", "content": "Bên B có quyền kiểm tra đột xuất phần mềm hệ thống của Bên A để xác thực số lượng người dùng thực tế không vượt quá số lượng 500 giấy phép được cấp. Nếu phát hiện số người dùng thực tế vượt quá, Bên A có trách nhiệm mua bổ sung giấy phép với đơn giá bằng 150% đơn giá chuẩn kèm theo mức phạt vi phạm sử dụng quá số lượng bằng 20% giá trị hợp đồng.", "type": "AUDIT"}
            ],
            "entities": [
                {"type": "CONTRACT_VALUE", "value": "300,000 USD", "norm": "300000"},
                {"type": "COMPANY_NAME", "value": "SAP Việt Nam", "norm": "SAP"}
            ],
            "analysis": {
                "score": Decimal("48.00"),
                "level": "LOW",
                "summary": "Hợp đồng cấp phép phần mềm ERP chứa điều khoản kiểm tra hệ thống (Audit) phổ biến của nhà cung cấp phần mềm quốc tế, có quy định phạt 20% nếu dùng quá số lượng cấp phép."
            },
            "findings": [
                {
                    "rule_name": "Phạt vi phạm & Bồi thường",
                    "clause_index": 0,
                    "score": Decimal("50.00"),
                    "level": "MEDIUM",
                    "explanation": "Quy định đơn giá mua bổ sung 150% đơn giá chuẩn và phạt thêm 20% là tương đối khắt khe đối với lỗi khai báo thừa số người dùng do sơ suất hành chính.",
                    "recommendation": "Yêu cầu quy định đơn giá bổ sung bằng đơn giá chuẩn, và chỉ áp dụng mức phạt 20% nếu phát hiện Bên A cố tình gian lận số lượng quy mô lớn.",
                    "party": "Bên A (FPT Software JSC)"
                }
            ]
        },
        {
            "code": "HOTEL-CONF-2026",
            "title": "Hợp đồng Dịch vụ Tổ chức Hội nghị Khách hàng FPT Techday 2026",
            "type": "Event Services",
            "value": Decimal("40000.00"),
            "tags": [tag_event],
            "parties": [
                {"name": "Công ty Cổ phần FPT Software (FPT Software JSC)", "tax_code": "0101248141", "email": "events@fpt-software.com", "phone": "02437689048", "type": "CUSTOMER"},
                {"name": "Công ty Cổ phần Khách sạn Hồng Ngọc (Hong Ngoc Hotel)", "tax_code": "0102719230", "email": "booking@hongngochotel.com.vn", "phone": "02439343355", "type": "HOTEL"}
            ],
            "text": """CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc
---
HỢP ĐỒNG DỊCH VỤ TỔ CHỨC SỰ KIỆN HỘI NGHỊ

Hôm nay, ngày 18 tháng 07 năm 2026, tại Hà Nội:
Bên A: Công ty Cổ phần FPT Software (FPT Software JSC)
Bên B: Công ty Cổ phần Khách sạn Hồng Ngọc (Hong Ngoc Hotel)

Điều 1: Dịch vụ cung cấp
Bên B chịu trách nhiệm cung cấp hội trường lớn sức chứa 500 khách, dịch vụ tiệc buffet trưa và các thiết bị âm thanh ánh sáng phục vụ hội nghị FPT Techday 2026 vào ngày 15 tháng 10 năm 2026.

Điều 2: Phí dịch vụ
Tổng giá trị dịch vụ trọn gói tạm tính là 40,000 USD (đã bao gồm các phí dịch vụ phòng hội nghị và ăn uống).

Điều 3: Hủy bỏ dịch vụ và Phạt hủy phòng (Cancellation Fees)
Bên A có quyền hủy bỏ hợp đồng bằng văn bản gửi cho Bên B. Nếu Bên A hủy hợp đồng trước ngày diễn ra sự kiện từ 30 đến 60 ngày, Bên A phải trả khoản phí hủy tương đương 50% tổng giá trị dịch vụ. Nếu hủy hợp đồng trong vòng 30 ngày trước sự kiện, Bên A phải bồi thường 100% tổng giá trị dịch vụ và không được hoàn lại tiền đặt cọc.""",
            "clauses": [
                {"title": "Điều 3: Hủy bỏ dịch vụ và Phạt hủy phòng (Cancellation Fees)", "content": "Nếu Bên A hủy hợp đồng trước ngày diễn ra sự kiện từ 30 đến 60 ngày, Bên A phải trả khoản phí hủy tương đương 50% tổng giá trị dịch vụ. Nếu hủy hợp đồng trong vòng 30 ngày trước sự kiện, Bên A phải bồi thường 100% tổng giá trị dịch vụ và không được hoàn lại tiền đặt cọc.", "type": "CANCELLATION"}
            ],
            "entities": [
                {"type": "CONTRACT_VALUE", "value": "40,000 USD", "norm": "40000"},
                {"type": "COMPANY_NAME", "value": "Hong Ngoc Hotel", "norm": "HONG_NGOC_HOTEL"}
            ],
            "analysis": {
                "score": Decimal("50.00"),
                "level": "MEDIUM",
                "summary": "Hợp đồng đặt phòng hội nghị sự kiện ghi nhận mức phí phạt hủy phòng lên tới 100% giá trị hợp đồng nếu hủy trong vòng 30 ngày trước ngày diễn ra."
            },
            "findings": [
                {
                    "rule_name": "Payment Risk",
                    "clause_index": 0,
                    "score": Decimal("55.00"),
                    "level": "MEDIUM",
                    "explanation": "Mức phạt hủy phòng 100% trong vòng 30 ngày trước sự kiện là tương đối khắt khe, không tạo điều kiện linh hoạt cho Bên A nếu phát sinh trường hợp khẩn cấp.",
                    "recommendation": "Đề xuất thương thảo giảm tỷ lệ phạt xuống 70% trong vòng 15 đến 30 ngày, và chỉ phạt 100% nếu hủy trong vòng 7 ngày trước sự kiện.",
                    "party": "Bên A (FPT Software JSC)"
                }
            ]
        }
    ]

    for data in contracts_data:
        # Delete if exists
        Contract.objects.filter(contract_code=data["code"]).delete()
        
        # Create Contract
        contract = Contract.objects.create(
            company=company,
            contract_code=data["code"],
            title=data["title"],
            contract_type=data["type"],
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timezone.timedelta(days=365),
            contract_value=data["value"],
            status='ANALYZED'
        )
        for t in data["tags"]:
            contract.tags.add(t)
            
        print(f"Created Contract: {contract.contract_code}")

        # Create Version
        version = ContractVersion.objects.create(
            contract=contract,
            version_number=1,
            file_hash=uuid.uuid4().hex[:32],
            change_summary='Khởi tạo bản ghi hợp đồng v1.0'
        )
        
        # Encrypt & save file on disk
        pdf_content = data["text"].encode('utf-8')
        encrypted_pdf = encrypt_pdf(pdf_content)
        file_name = f"contract_{data['code'].lower().replace('-', '_')}_v1.pdf"
        file_path = os.path.join(settings.MEDIA_ROOT, 'contracts', file_name)
        with open(file_path, 'wb') as f:
            f.write(encrypted_pdf)
            
        cf = ContractFile.objects.create(
            version=version,
            file_name=file_name,
            file_path=settings.MEDIA_URL + f"contracts/{file_name}",
            file_size=len(encrypted_pdf),
            mime_type='application/pdf'
        )
        
        # Create Parties
        for p in data["parties"]:
            ContractParty.objects.create(
                contract=contract,
                party_name=p["name"],
                tax_code=p["tax_code"],
                email=p["email"],
                phone=p["phone"],
                party_type=p["type"]
            )
            
        # Create Clauses
        created_clauses = []
        for cl in data["clauses"]:
            cls_obj = Clause.objects.create(
                version=version,
                clause_title=cl["title"],
                clause_content=cl["content"],
                clause_type=cl["type"]
            )
            created_clauses.append(cls_obj)
            
        # Create Extracted Entities
        for ent in data["entities"]:
            ExtractedEntity.objects.create(
                clause=created_clauses[0], # link to first clause
                entity_type=ent["type"],
                entity_value=ent["value"],
                normalized_value=ent["norm"],
                confidence_score=Decimal("0.95")
            )
            
        # Create AI Analysis
        analysis = AIAnalysis.objects.create(
            version=version,
            model_name=data["analysis"]["model_name"] if "model_name" in data["analysis"] else 'Qwen2.5-Contract-Finetuned',
            overall_score=data["analysis"]["score"],
            risk_level=data["analysis"]["level"],
            summary=data["analysis"]["summary"]
        )
        
        # Create Findings
        for fnd in data["findings"]:
            rule = RiskRule.objects.filter(rule_name=fnd["rule_name"]).first() or RiskRule.objects.filter(rule_name__icontains=fnd["rule_name"].split()[0]).first()
            if rule:
                RiskFinding.objects.create(
                    analysis=analysis,
                    clause=created_clauses[fnd["clause_index"]],
                    rule=rule,
                    risk_score=fnd["score"],
                    risk_level=fnd["level"],
                    explanation=fnd["explanation"],
                    recommendation=fnd["recommendation"],
                    disadvantaged_party=fnd["party"]
                )
                
        # Expert Review (Link to Doan2108)
        if user:
            from contracts.models import Review
            Review.objects.create(
                analysis=analysis,
                user=user,
                note='Đã kiểm tra báo cáo phân tích rủi ro tự động từ mô hình AI.',
                decision='APPROVED'
            )

        # Anchor to simulated blockchain database
        if conn:
            try:
                # Insert Hash Proof
                doc_hash = version.file_hash
                cursor.execute(
                    "INSERT INTO blockchain_hashproof (version_id, hash_algorithm, document_hash, generated_at, file_size, hash_version, verified, verified_at, merkle_root) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    [version.id, 'SHA-256', doc_hash, timezone.now(), len(encrypted_pdf), 1, True, timezone.now(), f"merkle_{data['code'].lower()}_root"]
                )
                proof_id = cursor.fetchone()[0]
                
                # Insert Transaction
                tx_hash = '0x' + uuid.uuid4().hex + uuid.uuid4().hex[:16]
                cursor.execute(
                    "INSERT INTO blockchain_blockchaintransaction (proof_id, network_id, smart_contract_id, tx_hash, block_hash, block_number, gas_fee, status, created_at, tx_type, channel_name, chaincode_name, retry_count) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    [proof_id, network_id, smart_contract_id, tx_hash, '0x' + uuid.uuid4().hex, 18900600 + len(data['code']), Decimal('0.00'), 'CONFIRMED', timezone.now(), 'INVOKE', 'contracts-channel', 'ContractVerifyChaincode', 0]
                )
                print(f"Anchored {data['code']} to blockchain. Tx: {tx_hash[:16]}")
                
            except Exception as b_ex:
                print(f"Warning: Failed to anchor {data['code']} to blockchain: {b_ex}")
                conn.rollback()
                
    if conn:
        conn.commit()
        cursor.close()
        conn.close()
        print("All blockchain records committed.")
        
    print("=== Diverse Contracts Seeding Completed Successfully ===")

if __name__ == '__main__':
    create_six_contracts()
