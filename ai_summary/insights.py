"""What can be said about a contract without the model: key dates, a preliminary summary, upload form suggestions."""
import calendar
import re
from datetime import date

import legal
from text_tools import amount_in, dates_in, durations_in, extract_facts, normalize, split_sections, stated_term

NOTICE = re.compile(r'báo trước[^.;\n]{0,20}?(\d+)\s*ngày|(\d+)\s*days?[^.;\n]{0,20}?notice', re.I)
TITLE = re.compile(r'^\W*(hop\s*dong|contract|agreement|thoa\s*thuan|phu\s*luc)')
PERIOD = re.compile(r'(?:từ|from)[^.;\n]{0,12}?(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}|\d{1,2}[ \t]+tháng[ \t]+\d{1,2}[ \t]+năm[ \t]+\d{4})'
                    r'[^.;\n]{0,20}?(?:đến|to|until)[^.;\n]{0,12}?(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}|\d{1,2}[ \t]+tháng[ \t]+\d{1,2}[ \t]+năm[ \t]+\d{4})', re.I)
VALUE_SENTENCE = re.compile(r'(?:tổng )?giá trị|tổng (?:số )?tiền|total (?:contract )?value|mức lương', re.I)
MONTHS = {'tháng': 1, 'năm': 12}
LABOR_ROLES = ((re.compile(r'^\W*nguoi\s*su\s*dung\s*lao\s*dong\W*[:：]'), 'Người sử dụng lao động'),
               (re.compile(r'^\W*nguoi\s*lao\s*dong\W*[:：]'), 'Người lao động'))


def _date(parts):
    try:
        return date(parts[2], parts[1], parts[0])
    except ValueError:
        return None


def _first_date(text):
    found = dates_in(text or '')
    return _date(found[0][0]) if found else None


def _after(start, number, unit):
    """Last day of a term starting on start: 12 tháng from 01/03/2025 ends 28/02/2026."""
    if unit in MONTHS:
        months = start.month - 1 + number * MONTHS[unit]
        year, month = start.year + months // 12, months % 12 + 1
        following = date(year, month, min(start.day, calendar.monthrange(year, month)[1]))
    elif unit == 'ngày':
        following = date.fromordinal(start.toordinal() + number)
    elif unit == 'tuần':
        following = date.fromordinal(start.toordinal() + 7 * number)
    else:
        return None
    return date.fromordinal(following.toordinal() - 1)


def key_dates(structured, source):
    """Start, end and notice period; an end date worked out from a duration is marked computed."""
    term, items = structured.get('term', ''), []
    found = [d for d in (_date(parts) for parts, _ in dates_in(term)) if d]
    start = found[0] if found else _first_date(structured.get('effective_date'))
    end = found[1] if len(found) > 1 else None
    computed = False
    durations = durations_in(term)
    if start and not end and durations:
        end = _after(start, *durations[0])
        computed = end is not None
    if start:
        items.append(dict(kind='start', label='Bắt đầu / hiệu lực', date=start.isoformat(), computed=False))
    if end:
        items.append(dict(kind='end', label='Kết thúc', date=end.isoformat(), computed=computed))
    termination = ' '.join(item.get('text', '') for item in structured.get('termination', []))
    notice = NOTICE.search(termination) or NOTICE.search(source)
    if notice:
        items.append(dict(kind='notice', label=f'Báo trước {notice.group(1) or notice.group(2)} ngày khi chấm dứt', date=None, computed=False))
    return items


def _labor_parties(source):
    found = []
    for line in source.splitlines():
        for pattern, role in LABOR_ROLES:
            if pattern.match(legal.fold(line)) and re.search(r'[:：]', line):
                found.append(f"{role}: {re.split(r'[:：]', line, maxsplit=1)[1].strip()}")
    return found


def preliminary(text):
    """Values copied from the source by regex, shown when the model is unreachable. Not a summary of meaning."""
    source = normalize(text)
    facts = extract_facts(source)
    # Labour contracts name their parties by role, which the Bên A/Bên B pattern in extract_facts does not cover.
    facts['parties'] = facts['parties'] or _labor_parties(source)
    facts['durations'] = facts['durations'] or [term for term in [stated_term(source)] if term]
    lines = []
    for label, key in (('Số hợp đồng', 'contract_numbers'), ('Các bên', 'parties'), ('Mã số thuế', 'tax_codes'),
                       ('Số tiền', 'money'), ('Ngày', 'dates'), ('Thời hạn', 'durations'), ('Tỷ lệ', 'percents')):
        if facts[key]:
            lines.append(f"{label}: {'; '.join(facts[key])}")
    if legal.is_labor_contract('', source):
        checklist = legal.labor_checklist(split_sections(source))
        gaps = [item['message'] for item in checklist['items'] if item['status'] != 'found']
        if gaps:
            lines += [f"Thiếu nội dung bắt buộc ({checklist['basis']}):"] + [f'  • {gap}' for gap in gaps]
    return '\n'.join(lines)


def _contract_type(title):
    """'HỢP ĐÔNG LAO ĐỘNG' -> 'Lao động', by position because OCR may have damaged the first words."""
    words = title.split()
    start = 2 if legal.fold(' '.join(words[:2])).replace(' ', '') == 'hopdong' else 1 if legal.fold(' '.join(words[:1])) == 'contract' else 0
    return ' '.join(words[start:]).capitalize()


def suggest(text):
    """Upload form values read from the document; the person reviews them before saving."""
    source = normalize(text)
    facts = extract_facts(source)
    # The title starts with the document type, so a clause like 'Điều 2. Thời hạn hợp đồng' is never taken for it.
    title = next((line.strip() for line in source.splitlines()[:15] if TITLE.match(legal.fold(line)) and 5 < len(line.strip()) <= 120), '')
    period = PERIOD.search(source)
    start, end = (_first_date(period.group(1)), _first_date(period.group(2))) if period else (None, None)
    value = next((amount_in(s[VALUE_SENTENCE.search(s).start():]) for s in re.split(r'(?<=[.;])\s+|\n', source)
                  if VALUE_SENTENCE.search(s) and amount_in(s[VALUE_SENTENCE.search(s).start():])), None)
    if not end and start is None:
        term = stated_term(source)
        start = _first_date(term)
    return dict(contract_code=facts['contract_numbers'][0] if facts['contract_numbers'] else '', title=title,
                contract_type=_contract_type(title),
                contract_value=value, start_date=start.isoformat() if start else '', end_date=end.isoformat() if end else '')
