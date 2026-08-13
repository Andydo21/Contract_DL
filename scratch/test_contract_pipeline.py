import os
import django
import sys

sys.path.append('d:\\Django_project\\RiskDL')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from document_processor.splitter.clause_splitter import ClauseSplitter
from document_processor.models.page import PageData

text = """CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
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
Bên A có quyền hủy bỏ hợp đồng bằng văn bản gửi cho Bên B. Nếu Bên A hủy hợp đồng trước ngày diễn ra sự kiện từ 30 đến 60 ngày, Bên A phải trả khoản phí hủy tương đương 50% tổng giá trị dịch vụ. Nếu hủy hợp đồng trong vòng 30 ngày trước sự kiện, Bên A phải bồi thường 100% tổng giá trị dịch vụ và không được hoàn lại tiền đặt cọc."""

pages = [PageData(page_number=1, text=text, source="pdf", confidence=1.0)]

splitter = ClauseSplitter()
clauses = splitter.split(pages)

with open('d:\\Django_project\\RiskDL\\scratch\\split_results.txt', 'w', encoding='utf-8') as f:
    f.write(f"Total clauses split: {len(clauses)}\n")
    for cl in clauses:
        f.write(f"\nTitle: {cl.title}\n")
        f.write(f"Pages: {cl.start_page} -> {cl.end_page}\n")
        f.write(f"Content:\n{cl.content}\n")
        f.write("-" * 50 + "\n")
