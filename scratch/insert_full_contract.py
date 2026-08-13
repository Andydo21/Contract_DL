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

def create_full_contract():
    print("=== Start Inserting Fully Loaded Contract ===")
    
    # 1. Fetch Company
    company = Company.objects.filter(company_name='FPT Software JSC').first()
    if not company:
        company = Company.objects.create(company_name='FPT Software JSC', tax_code='0101248141')
        print("Created company FPT Software JSC")
    
    # 2. Create Tags
    tag1, _ = Tag.objects.get_or_create(tag_name='Outsourcing')
    tag2, _ = Tag.objects.get_or_create(tag_name='Core-Banking')
    tag3, _ = Tag.objects.get_or_create(tag_name='High-Value')

    # 3. Create Contract
    contract_code = 'FPT-FULL-E2E-2026'
    # Delete if exists to make it re-runnable
    Contract.objects.filter(contract_code=contract_code).delete()
    
    contract = Contract.objects.create(
        company=company,
        contract_code=contract_code,
        title='Hợp đồng Phát triển Hệ thống Core-Banking (FPT & Techcombank)',
        contract_type='Software Services',
        start_date=timezone.now().date(),
        end_date=timezone.now().date() + timezone.timedelta(days=365),
        contract_value=Decimal('250000.00'),
        status='ANALYZED'
    )
    contract.tags.add(tag1, tag2, tag3)
    print(f"Created Contract: {contract.contract_code}")

    # 4. Create Contract Version & File
    version = ContractVersion.objects.create(
        contract=contract,
        version_number=1,
        file_hash='d3b07384d113edec49eaa6238ad5ff00',
        change_summary='Bản ký kết chính thức v1.0'
    )
    
    full_contract_text = """CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc
---

HỢP ĐỒNG CUNG CẤP DỊCH VỤ PHÁT TRIỂN PHẦN MỀM

- Căn cứ Bộ luật Dân sự nước Cộng hòa Xã hội Chủ nghĩa Việt Nam số 91/2015/QH13;
- Căn cứ Luật Thương mại nước Cộng hòa Xã hội Chủ nghĩa Việt Nam số 36/2005/QH11;
- Căn cứ vào nhu cầu và năng lực của hai bên.

Hôm nay, ngày 18 tháng 07 năm 2026, tại Hà Nội, chúng tôi gồm có:

BÊN A (BÊN KHÁCH HÀNG): NGÂN HÀNG TMCP KỸ THƯƠNG VIỆT NAM (TECHCOMBANK)
- Địa chỉ: Số 6 Quang Trung, Trần Hưng Đạo, Hoàn Kiếm, Hà Nội.
- Mã số thuế: 0100230800.
- Đại diện bởi: Ông Nguyễn Văn A - Chức vụ: Giám đốc Khối Công nghệ.

BÊN B (BÊN NHÀ CUNG CẤP): CÔNG TY CỔ PHẦN FPT SOFTWARE (FPT SOFTWARE JSC)
- Địa chỉ: Tòa nhà FPT, Phố Duy Tân, Dịch Vọng Hậu, Cầu Giấy, Hà Nội.
- Mã số thuế: 0101248141.
- Đại diện bởi: Ông Phạm Thanh B - Chức vụ: Tổng Giám đốc.

Hai bên thống nhất ký kết hợp đồng cung cấp dịch vụ phát triển hệ thống core-banking với các điều khoản chi tiết như sau:

Điều 1: Phạm vi công việc và dịch vụ bàn giao
Bên B chịu trách nhiệm tư vấn, thiết kế, phát triển và chuyển giao hệ thống phần mềm Core-Banking thế hệ mới cho Bên A. Phạm vi công việc bao gồm việc lập trình các phân hệ quản lý tài khoản, xử lý giao dịch trực tuyến, đối soát thẻ và hệ thống báo cáo quản trị theo tài liệu đặc tả kỹ thuật đính kèm Phụ lục 01. Bên B có trách nhiệm triển khai, chạy thử nghiệm hệ thống và đào tạo vận hành cho đội ngũ kỹ thuật của Bên A.

Điều 2: Giá trị hợp đồng và Phương thức thanh toán
Tổng giá trị hợp đồng trọn gói là 250,000 USD (Bằng chữ: Hai trăm năm mươi nghìn Đô la Mỹ). Giá trị trên đã bao gồm toàn bộ các chi phí dịch vụ, hỗ trợ kỹ thuật và các loại thuế phí theo quy định hiện hành. Bên A sẽ thực hiện thanh toán cho Bên B làm 3 đợt cụ thể: Đợt 1 thanh toán 30% trong vòng 10 ngày sau khi ký hợp đồng; Đợt 2 thanh toán 40% sau khi hoàn thành chạy thử nghiệm hệ thống; Đợt 3 thanh toán 30% còn lại trong vòng 15 ngày sau khi hai bên ký biên bản nghiệm thu bàn giao chính thức. Trong trường hợp Bên A chậm trễ thanh toán quá 5 ngày làm việc theo thời hạn quy định, Bên A sẽ phải chịu mức phạt lãi suất chậm trả 10% mỗi ngày tính trên tổng số tiền chậm trả của đợt thanh toán đó.

Điều 3: Quyền sở hữu trí tuệ
Mọi mã nguồn, tài liệu thiết kế, cơ sở dữ liệu và các sản phẩm trí tuệ khác được Bên B tạo ra hoặc phát triển riêng cho Bên A trong khuôn khổ hợp đồng này sẽ thuộc quyền sở hữu độc quyền của Bên A kể từ thời điểm Bên A hoàn tất nghĩa vụ thanh toán đợt cuối cùng. Bên B cam kết không vi phạm bất kỳ quyền sở hữu trí tuệ nào của bên thứ ba trong suốt quá trình thực hiện dự án và cam kết bồi thường toàn bộ thiệt hại cho Bên A nếu phát sinh các tranh chấp về bản quyền liên quan đến phần mềm đã bàn giao.

Điều 4: Bảo mật thông tin (Non-Disclosure Agreement)
Cả hai bên cam kết bảo mật tuyệt đối mọi thông tin kỹ thuật, thông tin kinh doanh, quy trình nghiệp vụ và dữ liệu khách hàng giao dịch qua hệ thống core-banking mà mình tiếp cận được trong quá trình hợp tác. Bên nhận thông tin không được sao chép, cung cấp hoặc tiết lộ bất kỳ thông tin mật nào cho bên thứ ba khi chưa có sự đồng ý bằng văn bản của bên tiết lộ. Mọi hành vi vi phạm thỏa thuận bảo mật này sẽ cấu thành lỗi nghiêm trọng và bên vi phạm phải chịu trách nhiệm bồi thường toàn bộ thiệt hại thực tế phát sinh cho bên bị vi phạm.

Điều 5: Cam kết chất lượng dịch vụ (SLA) và Giới hạn trách nhiệm bồi thường
Bên B cam kết thời gian hệ thống phần mềm hoạt động liên tục (Uptime) sau khi đưa vào vận hành thực tế đạt tối thiểu 99.9% tính theo tháng. Trong trường hợp xảy ra sự cố lỗi hệ thống nghiêm trọng thuộc trách nhiệm của Bên B làm ngưng trệ toàn bộ các giao dịch trực tuyến quá 2 giờ liên tục, Bên B sẽ phải bồi thường thiệt hại tối đa cho Bên A nhưng giới hạn bồi thường tối đa không vượt quá 5% tổng giá trị hợp đồng trong mọi trường hợp rủi ro hoặc lỗi phần mềm xảy ra.

Điều 6: Phạt vi phạm và Chấm dứt hợp đồng trước hạn
Trường hợp Bên B chậm trễ bàn giao hệ thống quá 30 ngày so với tiến độ cam kết tại Phụ lục dự án mà không do sự kiện bất khả kháng hoặc lỗi của Bên A, Bên A có quyền đơn phương chấm dứt hợp đồng bằng văn bản và Bên B sẽ phải hoàn trả toàn bộ số tiền Bên A đã tạm ứng trước đó đồng thời chịu phạt vi phạm hợp đồng bằng 8% giá trị hợp đồng.

Điều 7: Luật áp dụng và Giải quyết tranh chấp
Hợp đồng này được điều chỉnh và giải thích theo các quy định của pháp luật nước Cộng hòa Xã hội Chủ nghĩa Việt Nam. Mọi tranh chấp phát sinh từ hoặc liên quan đến hợp đồng này trước hết sẽ được giải quyết thông qua đàm phán hòa giải giữa hai bên. Trong trường hợp đàm phán không đạt kết quả trong vòng 30 ngày kể từ ngày phát sinh tranh chấp, một trong các bên có quyền đưa tranh chấp ra giải quyết tại Trung tâm Trọng tài Quốc tế Việt Nam (VIAC) bên cạnh Liên đoàn Thương mại và Công nghiệp Việt Nam theo Quy tắc tố tụng trọng tài của Trung tâm này.

Để làm bằng chứng, đại diện hợp pháp của hai bên đã ký và đóng dấu vào hợp đồng này. Hợp đồng được lập thành 04 bản tiếng Việt có giá trị pháp lý ngang nhau, mỗi bên giữ 02 bản để thực hiện.

ĐẠI DIỆN BÊN A
NGUYỄN VĂN A
(Đã ký tên và đóng dấu)

ĐẠI DIỆN BÊN B
PHẠM THANH B
(Đã ký tên và đóng dấu)"""
    
    from contracts.crypto_utils import encrypt_pdf
    pdf_content = full_contract_text.encode('utf-8')
    encrypted_pdf = encrypt_pdf(pdf_content)
    
    # Ensure media/contracts directory exists
    from django.conf import settings
    os.makedirs(os.path.join(settings.MEDIA_ROOT, 'contracts'), exist_ok=True)
    
    file_path = os.path.join(settings.MEDIA_ROOT, 'contracts', 'contract_core_banking_v1.pdf')
    with open(file_path, 'wb') as f:
        f.write(encrypted_pdf)
        
    cf = ContractFile.objects.create(
        version=version,
        file_name='contract_core_banking_v1.pdf',
        file_path=settings.MEDIA_URL + 'contracts/contract_core_banking_v1.pdf',
        file_size=len(encrypted_pdf),
        mime_type='application/pdf'
    )
    print("Created ContractVersion and encrypted ContractFile")

    # 5. Create Contract Parties
    ContractParty.objects.create(
        contract=contract,
        party_name='Ngân hàng TMCP Kỹ thương Việt Nam (Techcombank)',
        tax_code='0100230800',
        email='procurement@techcombank.com.vn',
        phone='1800588822',
        party_type='CLIENT'
    )
    ContractParty.objects.create(
        contract=contract,
        party_name='Công ty Cổ phần FPT Software (FPT Software JSC)',
        tax_code='0101248141',
        email='contracts@fpt-software.com',
        phone='02437689048',
        party_type='PROVIDER'
    )
    print("Created Contract Parties (Client: Techcombank, Provider: FPT Software)")

    # 6. Create Clauses
    c1 = Clause.objects.create(
        version=version,
        clause_title='Điều 2: Giá trị dịch vụ và Phương thức thanh toán',
        clause_content='Tổng giá trị hợp đồng là 250,000 USD. Techcombank sẽ thanh toán theo 3 đợt. Nếu Techcombank chậm thanh toán quá 5 ngày làm việc, Techcombank sẽ phải chịu mức phạt lãi suất 10% mỗi ngày tính trên số tiền chậm trả.',
        clause_type='PAYMENT'
    )
    c2 = Clause.objects.create(
        version=version,
        clause_title='Điều 5: Cam kết chất lượng dịch vụ (SLA)',
        clause_content='FPT Software cam kết thời gian hệ thống hoạt động liên tục (Uptime) đạt 99.9%. Trong trường hợp xảy ra lỗi hệ thống nghiêm trọng làm ngừng giao dịch quá 2 giờ, FPT Software sẽ phải bồi thường thiệt hại tối đa không vượt quá 5% giá trị hợp đồng.',
        clause_type='LIABILITY'
    )
    c3 = Clause.objects.create(
        version=version,
        clause_title='Điều 7: Bảo mật thông tin',
        clause_content='Cả hai bên cam kết bảo mật tuyệt đối các thông tin kinh doanh, dữ liệu khách hàng giao dịch qua hệ thống core-banking. Mọi hành vi vi phạm thỏa thuận bảo mật này sẽ phải bồi thường toàn bộ thiệt hại phát sinh thực tế.',
        clause_type='CONFIDENTIALITY'
    )
    c4 = Clause.objects.create(
        version=version,
        clause_title='Điều 10: Giải quyết tranh chấp',
        clause_content='Mọi tranh chấp phát sinh từ hoặc liên quan đến hợp đồng này trước hết sẽ được giải quyết thông qua thương lượng. Trường hợp thương lượng không thành công trong vòng 30 ngày, tranh chấp sẽ được đưa ra giải quyết tại Trung tâm Trọng tài Quốc tế Việt Nam (VIAC) theo Quy tắc tố tụng trọng tài của Trung tâm này.',
        clause_type='DISPUTE'
    )
    print("Created 4 contract clauses (Payment, Liability, Confidentiality, Dispute)")

    # 7. Create Extracted Entities
    ExtractedEntity.objects.create(
        clause=c1,
        entity_type='CONTRACT_VALUE',
        entity_value='250,000 USD',
        normalized_value='250000',
        confidence_score=Decimal('0.95')
    )
    ExtractedEntity.objects.create(
        clause=c1,
        entity_type='COMPANY_NAME',
        entity_value='Techcombank',
        normalized_value='TECHCOMBANK',
        confidence_score=Decimal('0.98')
    )
    ExtractedEntity.objects.create(
        clause=c2,
        entity_type='COMPANY_NAME',
        entity_value='FPT Software',
        normalized_value='FPT SOFTWARE',
        confidence_score=Decimal('0.98')
    )
    print("Created Extracted Entities")

    # 8. Create AI Analysis
    analysis = AIAnalysis.objects.create(
        version=version,
        model_name='Qwen2.5-Contract-Finetuned',
        overall_score=Decimal('68.50'),
        risk_level='HIGH',
        summary='Hợp đồng ghi nhận các điều khoản rủi ro mất cân đối cao nghiêng về phía khách hàng (Techcombank) liên quan đến điều khoản thanh toán phạt chậm trả quá cao (10%/ngày) và giới hạn bồi thường thiệt hại của nhà cung cấp quá thấp (5% giá trị hợp đồng).'
    )
    
    # 9. Create Risk Findings linked to real rules
    rule_liability = RiskRule.objects.filter(rule_name='Limitation of Liability Risk').first() or RiskRule.objects.filter(rule_name='Limitation of Liability Clause').first()
    rule_payment = RiskRule.objects.filter(rule_name='Payment Risk').first() or RiskRule.objects.filter(rule_name='Payment Terms & Milestones').first()
    rule_confidentiality = RiskRule.objects.filter(rule_name='Confidentiality Requirement').first() or RiskRule.objects.filter(rule_name='Bảo mật thông tin').first()
    rule_dispute = RiskRule.objects.filter(rule_name='Giải quyết tranh chấp').first() or RiskRule.objects.filter(rule_name='Mediation/Arbitration Risk').first()

    if rule_payment:
        RiskFinding.objects.create(
            analysis=analysis,
            clause=c1,
            rule=rule_payment,
            risk_score=Decimal('75.00'),
            risk_level='HIGH',
            explanation='Mức phạt thanh toán chậm 10%/ngày là cực kỳ cao và bất hợp lý, vượt quá quy định của Luật Thương mại Việt Nam (phạt vi phạm tối đa 8% giá trị phần nghĩa vụ bị vi phạm).',
            recommendation='Điều chỉnh mức phạt chậm thanh toán về mức 0.05%/ngày và tối đa không quá 8% tổng giá trị phần nghĩa vụ chậm thanh toán.',
            disadvantaged_party='Bên B (FPT Software JSC)'
        )
        
    if rule_liability:
        RiskFinding.objects.create(
            analysis=analysis,
            clause=c2,
            rule=rule_liability,
            risk_score=Decimal('80.00'),
            risk_level='HIGH',
            explanation='Giới hạn trách nhiệm bồi thường thiệt hại tối đa của FPT Software là 5% tổng giá trị hợp đồng là mức quá thấp, có khả năng không được khách hàng chấp nhận trong trường hợp xảy ra sự cố ngừng hệ thống giao dịch lớn gây thiệt hại nghiêm trọng.',
            recommendation='Tăng mức giới hạn bồi thường lên khoảng 50% đến 100% giá trị hợp đồng để đảm bảo tính khả thi và cân bằng lợi ích thương mại.',
            disadvantaged_party='Bên A (Techcombank)'
        )
        
    if rule_confidentiality:
        RiskFinding.objects.create(
            analysis=analysis,
            clause=c3,
            rule=rule_confidentiality,
            risk_score=Decimal('30.00'),
            risk_level='LOW',
            explanation='Điều khoản bảo mật yêu cầu bồi thường toàn bộ thiệt hại phát sinh thực tế. Đây là điều khoản tiêu chuẩn và an toàn cho cả hai bên.',
            recommendation='Giữ nguyên điều khoản này.',
            disadvantaged_party=None
        )
        
    if rule_dispute:
        RiskFinding.objects.create(
            analysis=analysis,
            clause=c4,
            rule=rule_dispute,
            risk_score=Decimal('20.00'),
            risk_level='LOW',
            explanation='Quy định giải quyết tranh chấp tại VIAC là điều khoản chuẩn và có tính pháp lý cao tại Việt Nam.',
            recommendation='Giữ nguyên điều khoản này.',
            disadvantaged_party=None
        )
    print("Created Risk Findings with detailed Vietnamese analysis")

    # 10. Create Expert Review
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.filter(username='Doan2108').first()
    if user:
        from contracts.models import Review
        Review.objects.create(
            analysis=analysis,
            user=user,
            note='Đồng ý với đánh giá rủi ro của AI. Đang chuẩn bị gửi đề xuất đàm phán lại các điều khoản thanh toán phạt chậm và giới hạn trách nhiệm bồi thường.',
            decision='APPROVED'
        )
        print(f"Created Expert Review by user {user.username}")

    # 11. Populate blockchain database using psycopg2
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
        
        # Insert Hash Proof
        document_hash = 'd3b07384d113edec49eaa6238ad5ff00'
        merkle_root = 'a84976cfab219dcb7689decf59828d11'
        
        # Check if hash proof exists
        cursor.execute("SELECT id FROM blockchain_hashproof WHERE version_id = %s", [version.id])
        row = cursor.fetchone()
        if row:
            cursor.execute("DELETE FROM blockchain_hashproof WHERE version_id = %s", [version.id])
            
        cursor.execute(
            "INSERT INTO blockchain_hashproof (version_id, hash_algorithm, document_hash, generated_at, file_size, hash_version, verified, verified_at, merkle_root) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            [version.id, 'SHA-256', document_hash, timezone.now(), len(encrypted_pdf), 1, True, timezone.now(), merkle_root]
        )
        proof_id = cursor.fetchone()[0]
        
        # Fetch or insert Blockchain Network
        cursor.execute("SELECT id FROM blockchain_blockchainnetwork LIMIT 1")
        row = cursor.fetchone()
        if row:
            network_id = row[0]
        else:
            cursor.execute(
                "INSERT INTO blockchain_blockchainnetwork (network_name, chain_type, rpc_endpoint, status) VALUES (%s, %s, %s, %s) RETURNING id",
                ['Hyperledger Fabric Client', 'FABRIC', 'http://fabric-gateway:5000', 'ACTIVE']
            )
            network_id = cursor.fetchone()[0]
            
        # Fetch or insert Smart Contract
        cursor.execute("SELECT id FROM blockchain_smartcontract WHERE network_id = %s LIMIT 1", [network_id])
        row = cursor.fetchone()
        if row:
            smart_contract_id = row[0]
        else:
            cursor.execute(
                "INSERT INTO blockchain_smartcontract (network_id, contract_address, contract_name, version, deployed_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                [network_id, 'contracts-channel', 'ContractVerifyChaincode', '1.0.0', timezone.now()]
            )
            smart_contract_id = cursor.fetchone()[0]
            
        # Insert Blockchain Transaction
        tx_hash = '0x' + uuid.uuid4().hex + uuid.uuid4().hex[:16]
        block_hash = '0x' + uuid.uuid4().hex
        block_number = 18900456
        
        cursor.execute(
            "INSERT INTO blockchain_blockchaintransaction (proof_id, network_id, smart_contract_id, tx_hash, block_hash, block_number, gas_fee, status, created_at, tx_type, channel_name, chaincode_name, fabric_tx_id, confirmation_time, latency, retry_count) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [proof_id, network_id, smart_contract_id, tx_hash, block_hash, block_number, Decimal('0.00'), 'CONFIRMED', timezone.now(), 'INVOKE', 'contracts-channel', 'ContractVerifyChaincode', tx_hash[2:], Decimal('1.200'), Decimal('1.200'), 0]
        )
        
        # Insert Audit Log
        cursor.execute(
            "INSERT INTO blockchain_blockchainaudit (transaction_id, user_id, company_id, ip, action, resource, before_state, after_state, status, created_at) VALUES ((SELECT id FROM blockchain_blockchaintransaction WHERE tx_hash = %s), %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [tx_hash, user.id if user else None, company.id, '127.0.0.1', 'Anchor Hash Proof', f"Contract v{version.id}", '{}', '{"status": "CONFIRMED"}', 'SUCCESS', timezone.now()]
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        print(f"Successfully anchored to simulated blockchain db (HashProof: {proof_id}, Tx: {tx_hash[:16]})")
        
    except Exception as ex:
        print(f"Warning: Failed to seed blockchain database: {ex}")
        
    print("=== Successfully Created Fully Loaded Contract FPT-FULL-E2E-2026 ===")

if __name__ == '__main__':
    create_full_contract()
