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

def create_diverse_contracts():
    print("=== Start Inserting Diverse Contracts ===")
    
    # ----------------------------------------------------
    # CONTRACT 1: LEASE-VIN-2026 (Office Lease Agreement)
    # ----------------------------------------------------
    comp_vingroup = Company.objects.filter(company_name='Vingroup Joint Stock Company').first()
    if not comp_vingroup:
        comp_vingroup = Company.objects.create(company_name='Vingroup Joint Stock Company', tax_code='0100798624')
    
    tag_lease, _ = Tag.objects.get_or_create(tag_name='Lease')
    tag_realestate, _ = Tag.objects.get_or_create(tag_name='Real-Estate')
    tag_metropolis, _ = Tag.objects.get_or_create(tag_name='Metropolis')
    
    contract_code_1 = 'LEASE-VIN-2026'
    Contract.objects.filter(contract_code=contract_code_1).delete()
    
    c1 = Contract.objects.create(
        company=comp_vingroup,
        contract_code=contract_code_1,
        title='Hợp đồng Thuê Văn phòng tại Vinhomes Metropolis Liễu Giai',
        contract_type='Lease Agreement',
        start_date=timezone.now().date(),
        end_date=timezone.now().date() + timezone.timedelta(days=730), # 2 years
        contract_value=Decimal('180000.00'),
        status='ANALYZED'
    )
    c1.tags.add(tag_lease, tag_realestate, tag_metropolis)
    print(f"Created Contract: {c1.contract_code}")

    version_1 = ContractVersion.objects.create(
        contract=c1,
        version_number=1,
        file_hash='f43d0473a218dbe8f731decc7462a11b',
        change_summary='Hợp đồng thuê văn phòng tầng 22'
    )
    
    text_lease = """CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc
---
HỢP ĐỒNG THUÊ VĂN PHÒNG KHÔNG GIAN THƯƠNG MẠI

Hôm nay, ngày 18 tháng 07 năm 2026, tại Hà Nội, chúng tôi gồm:

BÊN CHO THUÊ (BÊN A): CÔNG TY CỔ PHẦN VINHOMES (VINHOMES JSC)
- Địa chỉ: Tòa nhà Symphony, Chu Huy Mẫn, Vinhomes Riverside, Long Biên, Hà Nội.
- Mã số thuế: 0102671977.
- Đại diện bởi: Bà Nguyễn Thị C - Chức vụ: Giám đốc Khối Cho thuê thương mại.

BÊN THUÊ (BÊN B): CÔNG TY CỔ PHẦN FPT SOFTWARE (FPT SOFTWARE JSC)
- Địa chỉ: Tòa nhà FPT, Phố Duy Tân, Dịch Vọng Hậu, Cầu Giấy, Hà Nội.
- Mã số thuế: 0101248141.
- Đại diện bởi: Ông Phạm Thanh B - Chức vụ: Tổng Giám đốc.

Hai bên thống nhất thỏa thuận điều khoản thuê văn phòng tầng 22 tại tòa nhà Metropolis Liễu Giai:

Điều 1: Đối tượng thuê và Thời hạn thuê
Bên A đồng ý cho Bên B thuê toàn bộ diện tích sử dụng thực tế 350 m2 tại Tầng 22 Tòa văn phòng Metropolis, số 29 Liễu Giai, Ba Đình, Hà Nội. Mục đích thuê làm văn phòng làm việc. Thời hạn thuê là 02 (hai) năm kể từ ngày bàn giao mặt bằng.

Điều 2: Tiền đặt cọc và Phương thức thanh toán tiền thuê
Bên B có nghĩa vụ thanh toán khoản tiền đặt cọc bảo đảm tương đương với 03 (ba) tháng tiền thuê, bằng 22,500 USD trước ngày bàn giao mặt bằng. Tiền thuê văn phòng hàng tháng cố định là 7,500 USD (chưa bao gồm VAT và phí quản lý). Tiền thuê được thanh toán theo từng quý (3 tháng/lần) trước ngày mùng 5 của tháng đầu tiên trong quý thanh toán. Trường hợp Bên B chậm thanh toán tiền thuê quá 10 ngày so với thời hạn, Bên B sẽ phải chịu phạt chậm trả với lãi suất 5% mỗi ngày tính trên khoản tiền chậm nộp.

Điều 3: Phí quản lý và dịch vụ tiện ích
Ngoài tiền thuê văn phòng, Bên B có nghĩa vụ trực tiếp chi trả phí quản lý tòa nhà ở mức 5 USD/m2/tháng, tiền điện, nước sử dụng thực tế theo công tơ đo đếm và phí trông giữ phương tiện tại hầm tòa nhà theo bảng phí hiện hành do Ban Quản lý Metropolis ban hành.

Điều 4: Quyền đơn phương chấm dứt hợp đồng của Bên Cho Thuê
Bên A có quyền đơn phương chấm dứt hợp đồng trước thời hạn mà không cần bồi thường bất kỳ khoản chi phí nào, đồng thời được quyền giữ lại toàn bộ số tiền đặt cọc 03 tháng của Bên B trong các trường hợp sau: Bên B chậm thanh toán tiền thuê nhà quá 15 ngày làm việc; Bên B chuyển nhượng hoặc cho bên thứ ba thuê lại một phần hoặc toàn bộ mặt bằng văn phòng khi chưa có sự đồng ý bằng văn bản của Bên A.

Điều 5: Bàn giao mặt bằng khi chấm dứt hợp đồng
Khi chấm dứt thời hạn thuê theo hợp đồng hoặc khi bị chấm dứt trước hạn, Bên B có trách nhiệm dọn dẹp toàn bộ trang thiết bị nội thất di động của mình và bàn giao lại mặt bằng văn phòng cho Bên A ở trạng thái trống nguyên bản như khi nhận bàn giao trong vòng 07 ngày. Quá thời hạn này, toàn bộ tài sản còn lại của Bên B tại mặt bằng sẽ được coi là tài sản từ bỏ và Bên A có toàn quyền định đoạt hoặc tiêu hủy mà không chịu trách nhiệm bồi thường.

ĐẠI DIỆN BÊN A
NGUYỄN THỊ C

ĐẠI DIỆN BÊN B
PHẠM THANH B"""

    from contracts.crypto_utils import encrypt_pdf
    pdf_content_1 = text_lease.encode('utf-8')
    encrypted_pdf_1 = encrypt_pdf(pdf_content_1)
    
    # Ensure media/contracts directory exists
    from django.conf import settings
    os.makedirs(os.path.join(settings.MEDIA_ROOT, 'contracts'), exist_ok=True)
    
    file_path_1 = os.path.join(settings.MEDIA_ROOT, 'contracts', 'contract_office_lease_v1.pdf')
    with open(file_path_1, 'wb') as f:
        f.write(encrypted_pdf_1)
        
    cf1 = ContractFile.objects.create(
        version=version_1,
        file_name='contract_office_lease_v1.pdf',
        file_path=settings.MEDIA_URL + 'contracts/contract_office_lease_v1.pdf',
        file_size=len(encrypted_pdf_1),
        mime_type='application/pdf'
    )
    print("Created ContractFile for Lease Contract")

    # Contract Parties
    ContractParty.objects.create(
        contract=c1,
        party_name='Công ty Cổ phần Vinhomes (Vinhomes JSC)',
        tax_code='0102671977',
        email='leasing@vinhomes.vn',
        phone='1900232389',
        party_type='LESSOR'
    )
    ContractParty.objects.create(
        contract=c1,
        party_name='Công ty Cổ phần FPT Software (FPT Software JSC)',
        tax_code='0101248141',
        email='contracts@fpt-software.com',
        phone='02437689048',
        party_type='LESSEE'
    )

    # Clauses
    cl1 = Clause.objects.create(
        version=version_1,
        clause_title='Điều 2: Tiền đặt cọc và Phương thức thanh toán tiền thuê',
        clause_content='Bên B có nghĩa vụ thanh toán khoản tiền đặt cọc bảo đảm tương đương với 03 (ba) tháng tiền thuê, bằng 22,500 USD trước ngày bàn giao mặt bằng. Tiền thuê văn phòng hàng tháng cố định là 7,500 USD. Trường hợp Bên B chậm thanh toán tiền thuê quá 10 ngày so với thời hạn, Bên B sẽ phải chịu phạt chậm trả với lãi suất 5% mỗi ngày tính trên khoản tiền chậm nộp.',
        clause_type='PAYMENT'
    )
    cl2 = Clause.objects.create(
        version=version_1,
        clause_title='Điều 4: Quyền đơn phương chấm dứt hợp đồng của Bên Cho Thuê',
        clause_content='Bên A có quyền đơn phương chấm dứt hợp đồng trước thời hạn mà không cần bồi thường bất kỳ khoản chi phí nào, đồng thời được quyền giữ lại toàn bộ số tiền đặt cọc 03 tháng của Bên B trong các trường hợp sau: Bên B chậm thanh toán tiền thuê nhà quá 15 ngày làm việc; Bên B chuyển nhượng hoặc cho bên thứ ba thuê lại một phần hoặc toàn bộ mặt bằng văn phòng khi chưa có sự đồng ý bằng văn bản của Bên A.',
        clause_type='TERMINATION'
    )
    
    # Extracted Entities
    ExtractedEntity.objects.create(
        clause=cl1,
        entity_type='CONTRACT_VALUE',
        entity_value='180,000 USD',
        normalized_value='180000',
        confidence_score=Decimal('0.92')
    )
    ExtractedEntity.objects.create(
        clause=cl1,
        entity_type='COMPANY_NAME',
        entity_value='Vinhomes JSC',
        normalized_value='VINHOMES',
        confidence_score=Decimal('0.95')
    )

    # AI Analysis
    analysis_1 = AIAnalysis.objects.create(
        version=version_1,
        model_name='Qwen2.5-Contract-Finetuned',
        overall_score=Decimal('55.00'),
        risk_level='HIGH',
        summary='Hợp đồng thuê văn phòng chứa đựng các điều khoản bất lợi cực lớn cho bên thuê liên quan đến việc phạt chậm thanh toán 5%/ngày (tương đương 1825%/năm) và quyền tịch thu cọc 3 tháng chỉ sau 15 ngày chậm nộp tiền nhà của Bên Cho Thuê.'
    )
    
    rule_termination = RiskRule.objects.filter(rule_name='Unbalanced Termination Clause').first() or RiskRule.objects.filter(rule_name='Termination Clause').first()
    rule_payment = RiskRule.objects.filter(rule_name='Payment Risk').first() or RiskRule.objects.filter(rule_name='Payment Terms & Milestones').first()

    if rule_termination:
        RiskFinding.objects.create(
            analysis=analysis_1,
            clause=cl2,
            rule=rule_termination,
            risk_score=Decimal('90.00'),
            risk_level='HIGH',
            explanation='Điều khoản cho phép Bên A đơn phương chấm dứt và tịch thu cọc 3 tháng chỉ sau 15 ngày chậm trả là quá ngặt nghèo và không cân bằng đối với Bên B.',
            recommendation='Thỏa thuận nâng thời gian trễ hạn lên tối thiểu 30 ngày và quy định việc tịch thu cọc chỉ áp dụng nếu Bên B không khắc phục lỗi sau khi nhận văn bản cảnh báo 10 ngày.',
            disadvantaged_party='Bên B (FPT Software JSC)'
        )
        
    if rule_payment:
        RiskFinding.objects.create(
            analysis=analysis_1,
            clause=cl1,
            rule=rule_payment,
            risk_score=Decimal('85.00'),
            risk_level='HIGH',
            explanation='Lãi suất phạt chậm trả 5%/ngày là mức phạt đặc biệt nguy hiểm và phi thực tế, cao hơn hàng chục lần so với lãi suất phạt chậm trả thông dụng (0.03% - 0.05%/ngày).',
            recommendation='Điều chỉnh mức phạt chậm thanh toán về mức tối đa 0.05%/ngày hoặc theo lãi suất quá hạn của ngân hàng thương mại tại thời điểm vi phạm.',
            disadvantaged_party='Bên B (FPT Software JSC)'
        )

    # Expert Review
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.filter(username='Doan2108').first()
    if user:
        from contracts.models import Review
        Review.objects.create(
            analysis=analysis_1,
            user=user,
            note='Yêu cầu bộ phận Pháp chế đàm phán lại giảm tỷ lệ phạt chậm thanh toán xuống 0.05%/ngày và thời gian trễ hạn thanh toán trước khi chấm dứt lên 30 ngày.',
            decision='REJECTED'
        )

    # ----------------------------------------------------
    # CONTRACT 2: PURCHASE-VIET-2026 (Server Hardware Purchase)
    # ----------------------------------------------------
    comp_viettel = Company.objects.filter(company_name='Viettel Group').first()
    if not comp_viettel:
        comp_viettel = Company.objects.create(company_name='Viettel Group', tax_code='0100109106')
        
    tag_purchase, _ = Tag.objects.get_or_create(tag_name='Purchase')
    tag_hardware, _ = Tag.objects.get_or_create(tag_name='Hardware')
    tag_cisco, _ = Tag.objects.get_or_create(tag_name='Cisco')
    
    contract_code_2 = 'PURCHASE-VIET-2026'
    Contract.objects.filter(contract_code=contract_code_2).delete()
    
    c2 = Contract.objects.create(
        company=comp_viettel,
        contract_code=contract_code_2,
        title='Hợp đồng Mua bán Thiết bị Routing & Core-Switch Dự án Viettel IDC Bình Dương',
        contract_type='Purchase Agreement',
        start_date=timezone.now().date(),
        end_date=timezone.now().date() + timezone.timedelta(days=180), # 6 months
        contract_value=Decimal('350000.00'),
        status='ANALYZED'
    )
    c2.tags.add(tag_purchase, tag_hardware, tag_cisco)
    print(f"Created Contract: {c2.contract_code}")

    version_2 = ContractVersion.objects.create(
        contract=c2,
        version_number=1,
        file_hash='49f2b3e8e19e71cc32da84a6c9e01db1',
        change_summary='Hợp đồng cung cấp thiết bị Cisco Core Switch'
    )
    
    text_purchase = """CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc
---
HỢP ĐỒNG MUA BÁN THIẾT BỊ MẠNG CHUYÊN DỤNG

Hôm nay, ngày 18 tháng 07 năm 2026, tại Hà Nội, chúng tôi gồm:

BÊN MUA (BÊN A): TẬP ĐOÀN CÔNG NGHIỆP - VIỄN THÔNG QUÂN ĐỘI (VIETTEL)
- Địa chỉ: Lô D26 Khu đô thị mới Cầu Giấy, Yên Hòa, Cầu Giấy, Hà Nội.
- Mã số thuế: 0100109106.
- Đại diện bởi: Ông Nguyễn Văn D - Chức vụ: Phó Tổng Giám đốc Viettel Net.

BÊN BÁN (BÊN B): CÔNG TY TNHH CISCO SYSTEMS VIỆT NAM
- Địa chỉ: Tầng 15, Tòa nhà Saigon Tower, 29 Lê Duẩn, Quận 1, TP. Hồ Chí Minh.
- Mã số thuế: 0303248596.
- Đại diện bởi: Ông John Doe - Chức vụ: Giám đốc Kinh doanh Khu vực.

Hai bên thỏa thuận ký kết hợp đồng mua bán thiết bị định tuyến Cisco Core-Switch cho dự án Viettel IDC Bình Dương:

Điều 1: Danh mục thiết bị mua bán và chất lượng hàng hóa
Bên B cam kết cung cấp, bàn giao toàn bộ danh mục thiết bị bao gồm 04 thiết bị Cisco Nexus 9000 Series Core-Switch kèm theo modul quang học và bản quyền phần mềm điều hành nguyên đai nguyên kiện mới 100%, xuất xứ chính hãng Cisco Systems Mỹ/Singapore kèm theo chứng nhận CO, CQ đầy đủ.

Điều 2: Thời hạn giao hàng và Lắp đặt
Bên B có trách nhiệm vận chuyển hàng hóa, bàn giao và lắp đặt hoàn chỉnh tại trung tâm dữ liệu Viettel IDC Bình Dương trong vòng 90 ngày kể từ ngày hợp đồng có hiệu lực. Trong trường hợp Bên B chậm trễ giao hàng và lắp đặt quá thời hạn quy định, Bên B phải chịu mức phạt vi phạm chậm giao là 0.5% tổng giá trị hợp đồng cho mỗi ngày chậm giao và không giới hạn tổng giá trị phạt chậm giao.

Điều 3: Giá trị hợp đồng và Điều kiện thanh toán
Tổng giá trị hợp đồng là 350,000 USD (Bằng chữ: Ba trăm năm mươi nghìn Đô la Mỹ). Bên A sẽ thực hiện thanh toán cho Bên B như sau: Thanh toán 20% khi ký hợp đồng và nhận được bảo lãnh thực hiện hợp đồng của Bên B; Thanh toán 80% còn lại trong vòng 30 ngày làm việc sau khi hoàn tất nghiệm thu kỹ thuật và bàn giao ký biên bản kiểm thử E2E hệ thống mạng.

Điều 4: Bảo hành và Cam kết Hỗ trợ kỹ thuật (SLA)
Bên B cung cấp gói bảo hành chính hãng Cisco Smartnet 3 năm tận nơi cho toàn bộ thiết bị. Bên B cam kết cử kỹ sư hỗ trợ khắc phục sự cố kỹ thuật phần cứng trong vòng tối đa 04 giờ kể từ khi nhận được yêu cầu hỗ trợ từ Bên A. Trong trường hợp quá hạn 4 giờ mà thiết bị chưa được phục hồi hoạt động bình thường, Bên B sẽ bị phạt vi phạm $1,000 cho mỗi giờ lỗi kéo dài tiếp theo.

Điều 5: Quyền sở hữu trí tuệ phần mềm
Bên B cam kết cấp quyền sử dụng hệ điều hành Cisco IOS vĩnh viễn và không hủy ngang để vận hành hệ thống phần cứng đã cung cấp. Quyền sở hữu trí tuệ đối với phần mềm hệ điều hành thuộc về Cisco Systems. Bên A không được chuyển nhượng quyền sử dụng này cho bất kỳ bên thứ ba nào khác.

ĐẠI DIỆN BÊN A
NGUYỄN VĂN D

ĐẠI DIỆN BÊN B
JOHN DOE"""

    pdf_content_2 = text_purchase.encode('utf-8')
    encrypted_pdf_2 = encrypt_pdf(pdf_content_2)
    
    file_path_2 = os.path.join(settings.MEDIA_ROOT, 'contracts', 'contract_cisco_purchase_v1.pdf')
    with open(file_path_2, 'wb') as f:
        f.write(encrypted_pdf_2)
        
    cf2 = ContractFile.objects.create(
        version=version_2,
        file_name='contract_cisco_purchase_v1.pdf',
        file_path=settings.MEDIA_URL + 'contracts/contract_cisco_purchase_v1.pdf',
        file_size=len(encrypted_pdf_2),
        mime_type='application/pdf'
    )
    print("Created ContractFile for Purchase Contract")

    # Contract Parties
    ContractParty.objects.create(
        contract=c2,
        party_name='Tập đoàn Công nghiệp - Viễn thông Quân đội (Viettel)',
        tax_code='0100109106',
        email='netsupport@viettel.com.vn',
        phone='18008098',
        party_type='BUYER'
    )
    ContractParty.objects.create(
        contract=c2,
        party_name='Công ty TNHH Cisco Systems Việt Nam',
        tax_code='0303248596',
        email='contracts-support@cisco.com',
        phone='02838275555',
        party_type='SELLER'
    )

    # Clauses
    cl2_1 = Clause.objects.create(
        version=version_2,
        clause_title='Điều 2: Thời hạn giao hàng và Lắp đặt',
        clause_content='Bên B có trách nhiệm vận chuyển hàng hóa, bàn giao và lắp đặt hoàn chỉnh tại trung tâm dữ liệu Viettel IDC Bình Dương trong vòng 90 ngày. Trong trường hợp Bên B chậm trễ giao hàng và lắp đặt quá thời hạn quy định, Bên B phải chịu mức phạt vi phạm chậm giao là 0.5% tổng giá trị hợp đồng cho mỗi ngày chậm giao và không giới hạn tổng giá trị phạt chậm giao.',
        clause_type='PENALTY'
    )
    cl2_2 = Clause.objects.create(
        version=version_2,
        clause_title='Điều 4: Bảo hành và Cam kết Hỗ trợ kỹ thuật (SLA)',
        clause_content='Bên B cung cấp gói bảo hành chính hãng Cisco Smartnet 3 năm tận nơi cho toàn bộ thiết bị. Bên B cam kết cử kỹ sư hỗ trợ khắc phục sự cố kỹ thuật phần cứng trong vòng tối đa 04 giờ. Trong trường hợp quá hạn 4 giờ mà thiết bị chưa được phục hồi hoạt động bình thường, Bên B sẽ bị phạt vi phạm $1,000 cho mỗi giờ lỗi kéo dài tiếp theo.',
        clause_type='SLA'
    )

    # Extracted Entities
    ExtractedEntity.objects.create(
        clause=cl2_1,
        entity_type='CONTRACT_VALUE',
        entity_value='350,000 USD',
        normalized_value='350000',
        confidence_score=Decimal('0.96')
    )
    ExtractedEntity.objects.create(
        clause=cl2_1,
        entity_type='COMPANY_NAME',
        entity_value='Viettel Group',
        normalized_value='VIETTEL',
        confidence_score=Decimal('0.98')
    )

    # AI Analysis
    analysis_2 = AIAnalysis.objects.create(
        version=version_2,
        model_name='Qwen2.5-Contract-Finetuned',
        overall_score=Decimal('70.00'),
        risk_level='MEDIUM',
        summary='Hợp đồng mua bán máy chủ mạng chứa đựng các điều khoản phạt vi phạm chậm giao hàng không giới hạn trần phạt (uncapped) gây rủi ro tài chính cao cho bên bán (Cisco), và điều khoản phạt SLA $1,000/giờ sự cố kéo dài.'
    )
    
    rule_indemnity = RiskRule.objects.filter(rule_name='Broad Indemnification Clause').first() or RiskRule.objects.filter(rule_name='Phạt vi phạm & Bồi thường').first()
    rule_payment_terms = RiskRule.objects.filter(rule_name='Payment Risk').first() or RiskRule.objects.filter(rule_name='Payment Terms & Milestones').first()

    if rule_indemnity:
        RiskFinding.objects.create(
            analysis=analysis_2,
            clause=cl2_1,
            rule=rule_indemnity,
            risk_score=Decimal('75.00'),
            risk_level='HIGH',
            explanation='Điều khoản phạt chậm giao hàng 0.5%/ngày mà không giới hạn trần phạt tối đa (uncapped penalty) là cực kỳ bất lợi và vi phạm quy định giới hạn phạt tối đa 8% của Luật Thương mại Việt Nam.',
            recommendation='Thêm điều khoản giới hạn tổng mức phạt vi phạm chậm giao hàng không vượt quá 8% tổng giá trị hợp đồng theo đúng Luật Thương mại.',
            disadvantaged_party='Bên B (Cisco Systems)'
        )
        
    if rule_payment_terms:
        RiskFinding.objects.create(
            analysis=analysis_2,
            clause=cl2_2,
            rule=rule_payment_terms,
            risk_score=Decimal('60.00'),
            risk_level='MEDIUM',
            explanation='Mức phạt chậm khắc phục SLA $1,000/giờ là mức phạt cố định tương đối cao đối với các sự cố không thuộc nhóm khẩn cấp nghiêm trọng.',
            recommendation='Điều chỉnh mức phạt chỉ áp dụng đối với sự cố mức độ nghiêm trọng cấp 1 (P1 - Critical) và phân cấp giảm mức phạt đối với sự cố cấp độ thấp hơn.',
            disadvantaged_party='Bên B (Cisco Systems)'
        )

    # Expert Review
    if user:
        from contracts.models import Review
        Review.objects.create(
            analysis=analysis_2,
            user=user,
            note='Cần bổ sung giới hạn trần phạt vi phạm tối đa 8% tổng giá trị hợp đồng vào Điều 2 trước khi ký kết để đảm bảo tính tuân thủ pháp lý.',
            decision='APPROVED'
        )

    # ----------------------------------------------------
    # ANCHOR BOTH CONTRACTS TO BLOCKCHAIN DATABASE
    # ----------------------------------------------------
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
        
        # 1. Anchor LEASE-VIN-2026
        cursor.execute("SELECT id FROM blockchain_hashproof WHERE version_id = %s", [version_1.id])
        if cursor.fetchone():
            cursor.execute("DELETE FROM blockchain_hashproof WHERE version_id = %s", [version_1.id])
            
        cursor.execute(
            "INSERT INTO blockchain_hashproof (version_id, hash_algorithm, document_hash, generated_at, file_size, hash_version, verified, verified_at, merkle_root) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            [version_1.id, 'SHA-256', 'f43d0473a218dbe8f731decc7462a11b', timezone.now(), len(encrypted_pdf_1), 1, True, timezone.now(), 'merkle_lease_root_001']
        )
        proof_id_1 = cursor.fetchone()[0]
        
        # Network & Smart Contract (fetch existing)
        cursor.execute("SELECT id FROM blockchain_blockchainnetwork LIMIT 1")
        network_id = cursor.fetchone()[0]
        cursor.execute("SELECT id FROM blockchain_smartcontract LIMIT 1")
        smart_contract_id = cursor.fetchone()[0]
        
        tx_hash_1 = '0x' + uuid.uuid4().hex + uuid.uuid4().hex[:16]
        cursor.execute(
            "INSERT INTO blockchain_blockchaintransaction (proof_id, network_id, smart_contract_id, tx_hash, block_hash, block_number, gas_fee, status, created_at, tx_type, channel_name, chaincode_name, retry_count) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [proof_id_1, network_id, smart_contract_id, tx_hash_1, '0x' + uuid.uuid4().hex, 18900480, Decimal('0.00'), 'CONFIRMED', timezone.now(), 'INVOKE', 'contracts-channel', 'ContractVerifyChaincode', 0]
        )
        print(f"Anchored LEASE-VIN-2026 to Blockchain. Tx: {tx_hash_1[:16]}")
        
        # 2. Anchor PURCHASE-VIET-2026
        cursor.execute("SELECT id FROM blockchain_hashproof WHERE version_id = %s", [version_2.id])
        if cursor.fetchone():
            cursor.execute("DELETE FROM blockchain_hashproof WHERE version_id = %s", [version_2.id])
            
        cursor.execute(
            "INSERT INTO blockchain_hashproof (version_id, hash_algorithm, document_hash, generated_at, file_size, hash_version, verified, verified_at, merkle_root) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            [version_2.id, 'SHA-256', '49f2b3e8e19e71cc32da84a6c9e01db1', timezone.now(), len(encrypted_pdf_2), 1, True, timezone.now(), 'merkle_purchase_root_002']
        )
        proof_id_2 = cursor.fetchone()[0]
        
        tx_hash_2 = '0x' + uuid.uuid4().hex + uuid.uuid4().hex[:16]
        cursor.execute(
            "INSERT INTO blockchain_blockchaintransaction (proof_id, network_id, smart_contract_id, tx_hash, block_hash, block_number, gas_fee, status, created_at, tx_type, channel_name, chaincode_name, retry_count) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [proof_id_2, network_id, smart_contract_id, tx_hash_2, '0x' + uuid.uuid4().hex, 18900510, Decimal('0.00'), 'CONFIRMED', timezone.now(), 'INVOKE', 'contracts-channel', 'ContractVerifyChaincode', 0]
        )
        print(f"Anchored PURCHASE-VIET-2026 to Blockchain. Tx: {tx_hash_2[:16]}")
        
        conn.commit()
        cursor.close()
        conn.close()
        print("Blockchain anchoring completed successfully for both diverse contracts.")
        
    except Exception as ex:
        print(f"Warning: Failed to anchor to blockchain: {ex}")
        
    print("=== Diverse Contracts Seeding Completed Successfully ===")

if __name__ == '__main__':
    create_diverse_contracts()
