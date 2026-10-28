"""Domain knowledge kept out of the model: mandatory-content checklists and plain-language glossary.

Checks are keyword matches with the matching clause cited, not legal advice: a "missing" item means no
wording for it was found in the text, which the reader should confirm.
"""
import re

LABOR_CONTRACT = re.compile(r'hợp đồng lao động|người sử dụng lao động', re.I)

# Bộ luật Lao động 2019, Điều 21 khoản 1: nội dung chủ yếu của hợp đồng lao động.
# Each item: (point, label, [(part, pattern)]). An item is found when every part matches.
LABOR_ARTICLE_21 = [
    ('a', 'thông tin người sử dụng lao động và người giao kết', [
        ('tên, địa chỉ', r'địa chỉ|trụ sở'),
        ('người giao kết, chức danh', r'đại diện|chức vụ|chức danh')]),
    ('b', 'thông tin người lao động', [
        ('ngày sinh', r'ngày sinh|sinh ngày|năm sinh'),
        ('giới tính', r'giới tính|\bnam\b|\bnữ\b'),
        ('nơi cư trú', r'cư trú|thường trú|tạm trú|địa chỉ'),
        ('số CCCD/CMND/hộ chiếu', r'căn cước|cccd|cmnd|chứng minh nhân dân|hộ chiếu')]),
    ('c', 'công việc và địa điểm làm việc', [
        ('công việc', r'công việc|chức danh|vị trí'),
        ('địa điểm làm việc', r'địa điểm làm việc|nơi làm việc')]),
    ('d', 'thời hạn hợp đồng lao động', [
        ('thời hạn', r'thời hạn hợp đồng|xác định thời hạn|loại hợp đồng|thời hạn \d+ tháng|kể từ ngày .* đến ngày')]),
    ('đ', 'tiền lương', [
        ('mức lương', r'mức lương|lương cơ bản|lương chính|tiền lương'),
        ('hình thức trả lương', r'hình thức trả lương|trả lương bằng|chuyển khoản|tiền mặt'),
        ('thời hạn trả lương', r'thời hạn trả lương|kỳ trả lương|trả lương vào ngày|ngày \d+ hằng tháng|ngày \d+ hàng tháng')]),
    ('e', 'chế độ nâng bậc, nâng lương', [('nâng bậc, nâng lương', r'nâng bậc|nâng lương|tăng lương|xét lương')]),
    ('g', 'thời giờ làm việc, thời giờ nghỉ ngơi', [
        ('thời giờ làm việc', r'thời giờ làm việc|giờ làm việc|thời gian làm việc|giờ/ngày|giờ/tuần'),
        ('thời giờ nghỉ ngơi', r'nghỉ ngơi|nghỉ phép|phép năm|nghỉ lễ|nghỉ hằng tuần|nghỉ hàng tuần')]),
    ('h', 'trang bị bảo hộ lao động', [('bảo hộ lao động', r'bảo hộ lao động|trang bị bảo hộ|phương tiện bảo vệ cá nhân')]),
    ('i', 'bảo hiểm xã hội, bảo hiểm y tế, bảo hiểm thất nghiệp', [
        ('BHXH', r'bảo hiểm xã hội|bhxh'),
        ('BHYT', r'bảo hiểm y tế|bhyt'),
        ('BHTN', r'bảo hiểm thất nghiệp|bhtn')]),
    ('k', 'đào tạo, bồi dưỡng, nâng cao trình độ', [('đào tạo', r'đào tạo|bồi dưỡng|nâng cao trình độ|kỹ năng nghề')]),
]


def is_labor_contract(title, text):
    return bool(LABOR_CONTRACT.search(title or '') or
                (re.search(r'người lao động', text, re.I) and re.search(r'người sử dụng lao động', text, re.I)))


def labor_checklist(sections):
    """Each Article 21(1) item with status found/partial/missing and the clause where its wording appears."""
    results = []
    for point, label, parts in LABOR_ARTICLE_21:
        found, missing, cited = [], [], []
        for part, pattern in parts:
            section = next((s for s in sections if re.search(pattern, s['text'], re.I)), None)
            (found if section else missing).append(part)
            if section and section['label'] not in cited:
                cited.append(section['label'])
        status = 'found' if not missing else 'partial' if found else 'missing'
        message = ('' if status == 'found' else f'Không thấy nội dung về {label}' if status == 'missing'
                   else f"Thiếu {', '.join(missing)} ({label})")
        results.append(dict(point=point, label=label, status=status, found=found, missing=missing,
                            sections=cited, message=message))
    return dict(basis='Điều 21 khoản 1 BLLĐ 2019, đối chiếu theo từ khóa', items=results)


# (pattern, explanation). Explanations are short and general; they describe the term, not this contract.
GLOSSARY = [
    (r'đơn phương chấm dứt', 'một bên tự kết thúc hợp đồng mà không cần bên kia đồng ý'),
    (r'bất khả kháng', 'sự kiện khách quan không lường trước, không khắc phục được như thiên tai, dịch bệnh'),
    (r'phạt vi phạm', 'khoản tiền bên vi phạm phải trả theo mức đã thỏa thuận trong hợp đồng'),
    (r'bồi thường(?: toàn bộ)? thiệt hại', 'trả tiền bù cho tổn thất thực tế mà bên kia phải chịu'),
    (r'tạm ứng', 'trả trước một phần tiền trước khi công việc hoàn thành'),
    (r'nghiệm thu', 'kiểm tra và xác nhận hàng hóa hoặc công việc đạt yêu cầu'),
    (r'thanh lý(?: hợp đồng)?', 'thủ tục hai bên xác nhận đã xong nghĩa vụ và khép lại hợp đồng'),
    (r'(?:tiền )?đặt cọc', 'khoản tiền giao trước để bảo đảm thực hiện hợp đồng; bên vi phạm có thể mất hoặc phải trả thêm tiền cọc'),
    (r'lãi chậm trả', 'tiền lãi phải trả thêm khi thanh toán trễ hạn'),
    (r'bảo lãnh', 'bên thứ ba, thường là ngân hàng, cam kết trả thay nếu một bên không thực hiện nghĩa vụ'),
    (r'giữ lại làm bảo hành', 'phần tiền chưa trả ngay, giữ lại đến khi hết thời gian bảo hành'),
    (r'trọn gói', 'giá cố định, không điều chỉnh khi khối lượng thay đổi'),
    (r'bàn giao mặt bằng', 'giao địa điểm để bắt đầu thi công'),
    (r'hóa đơn hợp lệ', 'hóa đơn lập đúng quy định về thuế'),
    (r'\bVAT\b', 'thuế giá trị gia tăng'),
    (r'trọng tài', 'giải quyết tranh chấp bằng trọng tài viên thay cho tòa án'),
    (r'vi phạm (?:nghiêm trọng|cơ bản)', 'vi phạm khiến bên kia không đạt được mục đích ký hợp đồng'),
    (r'thử việc', 'thời gian làm thử trước khi làm việc chính thức'),
    (r'trợ cấp thôi việc', 'khoản tiền người sử dụng lao động trả khi người lao động nghỉ việc đủ điều kiện'),
    (r'hợp đồng lao động không xác định thời hạn', 'hợp đồng không ghi ngày kết thúc'),
    (r'hợp đồng lao động xác định thời hạn', 'hợp đồng có ngày kết thúc, tối đa 36 tháng'),
    (r'bảo hiểm xã hội|\bBHXH\b', 'bảo hiểm bắt buộc chi trả khi ốm đau, thai sản, tai nạn lao động, hưu trí'),
    (r'bảo hiểm thất nghiệp|\bBHTN\b', 'bảo hiểm hỗ trợ tiền khi mất việc'),
    (r'phụ cấp', 'khoản tiền trả thêm ngoài lương chính'),
    # Longest phrase first: the explanation goes after "nghỉ phép năm", not inside it.
    (r'nghỉ phép năm|phép năm|nghỉ phép','ngày nghỉ vẫn được hưởng lương'),
    (r'người sử dụng lao động', 'bên thuê và trả lương cho người lao động'),
]


def explain_terms(lines):
    """Append a plain-language explanation after the first use of each glossary term."""
    used = set()
    explained = []
    for line in lines:
        # Matches are found in the original line only, so an inserted explanation is never re-explained.
        inserts = []
        for index, (pattern, meaning) in enumerate(GLOSSARY):
            match = None if index in used else re.search(pattern, line, re.I)
            if match and not any(start <= match.start() < end for start, end, _ in inserts):
                used.add(index)
                inserts.append((match.start(), match.end(), meaning))
        for _, end, meaning in sorted(inserts, reverse=True):
            line = f'{line[:end]} (nghĩa là: {meaning}){line[end:]}'
        explained.append(line)
    return explained
