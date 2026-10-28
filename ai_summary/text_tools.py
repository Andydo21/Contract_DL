"""Deterministic contract text handling: sections, exact facts and number verification."""
import re
import unicodedata

HEADING = re.compile(r'^[ \t]*(?:[#*]+[ \t]*)?((?:ĐIỀU|Điều|điều|ARTICLE|Article)[ \t]+(\d+|[IVXLC]+)\b[ \t.:\-–]*(.*))$', re.M)
# Sections whose content decides value, money flow, term and liability are kept first when trimming.
PRIORITY = re.compile(r'giá trị|thanh toán|tạm ứng|thời hạn|hiệu lực|phạt|bồi thường|chấm dứt|đơn phương|'
                      r'bảo hành|nghiệm thu|giao hàng|bất khả kháng|tranh chấp|trách nhiệm|nghĩa vụ|quyền', re.I)

MONEY = re.compile(r'\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?[ \t]*(?:đồng|VNĐ|VND|vnđ|USD|EUR|đ\b)'
                   r'|\d+(?:[.,]\d+)?[ \t]*(?:tỷ|triệu|nghìn|ngàn)[ \t]*(?:đồng|VNĐ|VND)?', re.I)
DATE = re.compile(r'\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}\b|ngày[ \t]+\d{1,2}[ \t]+tháng[ \t]+\d{1,2}[ \t]+năm[ \t]+\d{4}', re.I)
DURATION = re.compile(r'(?:trong(?:[ \t]+vòng)?|thời hạn(?:[ \t]+là)?|sau|kể từ|tối đa|chậm nhất)[ \t]+'
                      r'(?:\(?\d+\)?[ \t]*(?:\([^)]{0,20}\)[ \t]*)?)(?:ngày|tháng|năm|tuần)(?:[ \t]+(?:làm việc|dương lịch))?'
                      r'|\d+[ \t]*(?:ngày|tháng|năm|tuần)(?:[ \t]+(?:làm việc|dương lịch))?[ \t]+kể từ[^.;,\n]{0,40}', re.I)
PERCENT = re.compile(r'\d+(?:[.,]\d+)?[ \t]*%')
TAX_CODE = re.compile(r'(?:MST|Mã số thuế|Mã số doanh nghiệp)[ \t]*[:：]?[ \t]*(\d{10}(?:-\d{3})?)(?!\d)', re.I)
REPRESENTATIVE = re.compile(r'(?:Người đại diện|Đại diện)(?:[ \t]+(?:theo pháp luật|bởi))?[ \t]*[:：][ \t]*([^\n]{2,80})', re.I)
CONTRACT_NO = re.compile(r'(?:Hợp đồng số|HĐ số|Số)[ \t]*[:：][ \t]*([\w][\w/.\-]{2,40})', re.I)
PARTY = re.compile(r'^[ \t]*((?:BÊN|Bên)[ \t]+(?:[A-ZĐ]\b|[^\n:：]{2,25}?))[ \t]*(?:\([^)\n]*\))?[ \t]*[:：][ \t]*(\S[^\n]{2,150})$', re.M)
NUMBER = re.compile(r'\d+(?:[.,]\d+)*')


def normalize(text):
    """NFC plus collapsed spacing; OCR output often mixes decomposed accents and stray blanks."""
    text = unicodedata.normalize('NFC', text or '').replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'[ \t ]+', ' ', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def split_sections(text, fallback_size=2500):
    """Split on Điều/Article headings; S0 is the preamble with title and parties."""
    text = normalize(text)
    marks = list(HEADING.finditer(text))
    if not marks:
        parts, current = [], ''
        for paragraph in text.split('\n\n'):
            if current and len(current) + len(paragraph) > fallback_size:
                parts.append(current)
                current = ''
            current = f'{current}\n\n{paragraph}' if current else paragraph
        if current:
            parts.append(current)
        return [dict(id=f'S{i}', label='Phần mở đầu' if i == 0 else f'Đoạn {i}', text=part.strip())
                for i, part in enumerate(parts)]
    sections = []
    if text[:marks[0].start()].strip():
        sections.append(dict(id='S0', label='Phần mở đầu', text=text[:marks[0].start()].strip()))
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        sections.append(dict(id=f'S{len(sections)}', label=f'Điều {mark.group(2)}', text=text[mark.start():end].strip()))
    return sections


def _unique(values, limit=12):
    seen, result = set(), []
    for value in values:
        value = ' '.join(value.split()).strip(' .,;')
        if value and value.lower() not in seen:
            seen.add(value.lower())
            result.append(value)
    return result[:limit]


def extract_facts(text):
    """Exact values copied from the source; the model gets them as anchors, never as claims to invent from."""
    text = normalize(text)
    return dict(
        contract_numbers=_unique(CONTRACT_NO.findall(text[:3000]), 3),
        parties=_unique(f'{role.strip()}: {name.strip()}' for role, name in PARTY.findall(text)),
        tax_codes=_unique(TAX_CODE.findall(text)),
        money=_unique(MONEY.findall(text)),
        dates=_unique(DATE.findall(text)),
        durations=_unique(DURATION.findall(text)),
        percents=_unique(PERCENT.findall(text)),
    )


DATE_PARTS = re.compile(r'\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\b|(?:ngày[ \t]+)?\b(\d{1,2})[ \t]+tháng[ \t]+(\d{1,2})[ \t]+năm[ \t]+(\d{4})', re.I)
EFFECTIVE = re.compile(r'hiệu lực|effective', re.I)


def dates_in(text):
    """(day, month, year) for each numeric or spelled-out Vietnamese date, with its source text."""
    return [((int(m[1] or m[4]), int(m[2] or m[5]), int(m[3] or m[6])), m.group(0)) for m in DATE_PARTS.finditer(text)]


def effective_dates(source):
    """Dates stated in sentences about when the contract takes effect, and whether signing is the trigger."""
    sentences = [s for s in re.split(r'(?<=[.;])\s+|\n', source) if EFFECTIVE.search(s)]
    return ([d for s in sentences for d in dates_in(s)],
            any(re.search(r'ngày ký|date of signing|upon signing', s, re.I) for s in sentences))


def party_details(source, names):
    """Tax code and representative read from the source block of each party.

    A party's block runs from the first mention of its name to the first mention of the next party
    (or 800 characters). Values outside the block belong to someone else and are never attributed.
    """
    positions = {}
    for name in names:
        match = re.search(re.escape(' '.join(name.split())), source, re.I) if name.strip() else None
        positions[name] = match.start() if match else None
    details = {}
    for name, start in positions.items():
        if start is None:
            details[name] = None
            continue
        end = min([p for p in positions.values() if p is not None and p > start] + [start + 800])
        block = source[start:end]
        tax = TAX_CODE.search(block)
        rep = REPRESENTATIVE.search(block)
        details[name] = dict(tax_code=tax.group(1) if tax else '',
                             representative=rep.group(1).strip(' .;,') if rep else '')
    return details


def chunk_sections(sections, max_chars, max_chunks):
    """Group whole sections into chunks; over the cap, keep the preamble and priority sections first."""
    sections = [dict(s, text=s['text'][:max_chars]) for s in sections]
    ranked = sorted(sections, key=lambda s: (s['id'] != 'S0', not PRIORITY.search(s['text'][:300]),
                                             -len(PRIORITY.findall(s['text']))))
    keep, used = set(), 0
    for section in ranked:
        if used + len(section['text']) <= max_chars * max_chunks:
            keep.add(section['id'])
            used += len(section['text'])
    while True:
        chunks = _pack([s for s in sections if s['id'] in keep], max_chars)
        if len(chunks) <= max_chunks:
            return chunks
        # Whole sections leave gaps when packed; shed the lowest-ranked one and repack.
        keep.discard(next(s['id'] for s in reversed(ranked) if s['id'] in keep))


def _pack(sections, max_chars):
    chunks, current, size = [], [], 0
    for section in sections:
        if current and size + len(section['text']) > max_chars:
            chunks.append(current)
            current, size = [], 0
        current.append(section)
        size += len(section['text'])
    if current:
        chunks.append(current)
    return chunks


AMOUNT = re.compile(r'(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)[ \t]*(tỷ|triệu|nghìn|ngàn)?', re.I)
SCALE = {'tỷ': 10 ** 9, 'triệu': 10 ** 6, 'nghìn': 10 ** 3, 'ngàn': 10 ** 3}
DURATION_PARTS = re.compile(r'(\d+)[ \t]*(ngày|tháng|năm|tuần|days?|months?|years?)', re.I)
UNITS = {'day': 'ngày', 'days': 'ngày', 'month': 'tháng', 'months': 'tháng', 'year': 'năm', 'years': 'năm'}


def amount_in(text):
    """First money-sized amount in text: '12.500.000 đ' -> 12500000, '1,5 tỷ' -> 1500000000; None if absent."""
    for match in AMOUNT.finditer(text or ''):
        digits, scale = match.group(1), SCALE.get((match.group(2) or '').lower(), 1)
        if re.fullmatch(r'\d{1,3}(?:[.,]\d{3})+', digits):
            value = int(re.sub(r'[.,]', '', digits))
        else:
            value = float(digits.replace(',', '.'))
        value *= scale
        if value >= 1000:
            return int(value)
    return None


def durations_in(text):
    """[(number, unit)] with English units mapped to Vietnamese."""
    return [(int(n), UNITS.get(u.lower(), u.lower())) for n, u in DURATION_PARTS.findall(text or '')]


TERM_SENTENCE = re.compile(r'thời hạn (?:của )?hợp đồng|thời gian (?:thực hiện|thi công)|hợp đồng có hiệu lực|'
                           r'thời hạn thuê|has a term of', re.I)


def stated_term(source):
    """'180 ngày kể từ ngày bàn giao mặt bằng' from the sentence that states the contract's duration, or ''."""
    for sentence in re.split(r'(?<=[.;])\s+|\n', source):
        keyword = TERM_SENTENCE.search(sentence)
        duration = DURATION_PARTS.search(sentence, keyword.end()) if keyword else None
        if duration:
            return sentence[duration.start():].strip().rstrip('.;')[:160]
    return ''


def money(value):
    return f'{value:,}'.replace(',', '.')


def number_tokens(text):
    """Numbers without grouping separators or leading zeros: '1.500.000' -> '1500000', '03' -> '3'."""
    return {re.sub(r'[.,]', '', token).lstrip('0') or '0' for token in NUMBER.findall(text or '')}


def unsupported_numbers(text, source_numbers):
    return sorted(number_tokens(text) - source_numbers)
