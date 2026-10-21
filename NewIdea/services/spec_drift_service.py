"""Evidence-bound CAD-export/SOP checks; differences are reviewer candidates."""
import hashlib
import re
import unicodedata
from decimal import Decimal
from urllib.parse import urlsplit, urlunsplit
from NewIdea.repositories import contract_repository

PART = re.compile(r'(?:part\s*(?:number|no\.?|id)|mã\s*(?:linh kiện|chi tiết))\s*[:=]\s*([\w.-]+)', re.I)
FIELD = re.compile(r'^\s*([^:=\n]{2,60})\s*[:=]\s*(\S[^\n]{0,150})$', re.M)
UNITS = {'mm': ('length', Decimal('1')), 'cm': ('length', Decimal('10')),
         'm': ('length', Decimal('1000')), 'v': ('voltage', Decimal('1')),
         'kv': ('voltage', Decimal('1000')), 'nm': ('torque', Decimal('1')),
         'n.m': ('torque', Decimal('1')), 'n·m': ('torque', Decimal('1')),
         'pa': ('pressure', Decimal('1')), 'kpa': ('pressure', Decimal('1000')),
         'mpa': ('pressure', Decimal('1000000'))}
FIELDS = {'material', 'vật liệu', 'voltage', 'điện áp', 'torque', 'mô men', 'mô-men',
          'diameter', 'đường kính', 'length', 'chiều dài', 'pressure', 'áp suất'}
ALIASES = {'vật liệu': 'material', 'điện áp': 'voltage', 'mô men': 'torque', 'mô-men': 'torque',
           'đường kính': 'diameter', 'chiều dài': 'length', 'áp suất': 'pressure'}
DIMENSIONS = {'voltage': 'voltage', 'torque': 'torque', 'pressure': 'pressure',
              'diameter': 'length', 'length': 'length'}


def normalized(text):
    return ' '.join(unicodedata.normalize('NFC', text).casefold().split())


def grounding(record):
    box = record.get('bbox') or []
    valid = (len(box) == 4 and all(isinstance(x, (int, float)) and not isinstance(x, bool)
             and 0 <= x <= 1000 for x in box) and box[0] < box[2] and box[1] < box[3])
    url = record.get('source_url', '')
    identity = record.get('chunk_id', '')
    if valid and record.get('image_path') and identity.startswith('block:'):
        parts = urlsplit(url)
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, 'block-'+identity.split(':', 1)[1]))
        status = 'source_block_bbox'
    else:
        box, status = [], 'bbox_unavailable'
    return dict(source_id=identity, text=record.get('text', ''), page_number=record.get('page_number'),
                bbox=box, grounding_status=status, source_url=url,
                precision='block_region_not_individual_value', version_id=record.get('version_id'),
                contract_id=record.get('contract_id'), original_name=record.get('original_name', ''),
                source_location=record.get('source_location', ''), image_path=record.get('image_path', ''))


def specifications(records):
    document_parts = set(p.upper() for r in records for p in PART.findall(r.get('text', '')))
    found = []
    for record in records:
        local = set(p.upper() for p in PART.findall(record.get('text', '')))
        subjects = local or document_parts
        # Multiple possible parts require explicit per-record association.
        subject = next(iter(subjects)) if len(subjects) == 1 else None
        for match in FIELD.finditer(record.get('text', '')):
            label, value = normalized(match[1]), match[2].strip()
            if label not in FIELDS:
                continue
            found.append(dict(subject=subject, field=ALIASES.get(label, label), value=value,
                              quote=match[0].strip(), source=grounding(record)))
    return found


def comparable(value):
    text = normalized(value)
    match = re.fullmatch(r'([+-]?\d+(?:\.\d+)?)\s*([a-z·.]+)', text)
    if match and match[2] in UNITS:
        dimension, factor = UNITS[match[2]]
        return dimension, Decimal(match[1])*factor
    return None


def duplicate_check(left, right):
    texts = [normalized('\n'.join(r.get('text', '') for r in records)) for records in (left, right)]
    if not all(len(t) >= 80 and len(t.split()) >= 15 for t in texts):
        return dict(status='insufficient_text')
    hashes = [hashlib.sha256(t.encode()).hexdigest() for t in texts]
    if hashes[0] == hashes[1]:
        return dict(status='same_extracted_text', hashes=hashes, binary_identical=False)
    def shingles(text):
        words = text.split()
        return {tuple(words[i:i+4]) for i in range(len(words)-3)}
    a, b = map(shingles, texts)
    score = len(a & b)/max(1, len(a | b))
    return dict(status='similar_text_review_required' if score >= .85 else 'different_text',
                similarity=round(score, 4), score_kind='text_shingle_overlap_not_probability', hashes=hashes)


def compare_sources(left, right):
    a, b = specifications(left), specifications(right)
    differences, compared, ambiguous = [], 0, 0
    for x in a:
        if not x['subject']:
            ambiguous += 1
            continue
        targets = [y for y in b if y['subject'] == x['subject'] and y['field'] == x['field']]
        same_side = [y for y in a if y['subject'] == x['subject'] and y['field'] == x['field']]
        if len(targets) != 1 or len(same_side) != 1:
            ambiguous += 1
            continue
        y = targets[0]
        if normalized(x['value']) == normalized(y['value']):
            compared += 1
            continue
        xv, yv = comparable(x['value']), comparable(y['value'])
        if x['field'] != 'material' and (not xv or not yv or xv[0] != yv[0]
                                       or xv[0] != DIMENSIONS.get(x['field'])):
            ambiguous += 1
            continue
        compared += 1
        if xv and yv and xv == yv:
            continue
        differences.append(dict(subject=x['subject'], field=x['field'], left=x, right=y,
            status='spec_difference_requires_review', reason='same_explicit_part_and_field_different_value',
            semantic_conflict_verified=False))
    return dict(success=True, differences=differences, duplicate=duplicate_check(left, right),
        coverage=dict(left_specs=len(a), right_specs=len(b), compared_pairs=compared,
                      ambiguous_specs=ambiguous, drawing_geometry_analyzed=False),
        conclusion='review_required' if differences else 'no_difference_in_comparable_fields_not_proof_of_consistency')


def compare_versions(user, left_id, right_id):
    if type(left_id) is not int or type(right_id) is not int or left_id == right_id:
        raise ValueError('Chọn hai phiên bản tài liệu khác nhau.')
    left = contract_repository.get_visible_version(user, left_id)
    right = contract_repository.get_visible_version(user, right_id)
    for version in (left, right):
        if not contract_repository.completed_extraction_run(version):
            raise ValueError('Cần trích xuất cả hai tài liệu bằng A3 trước khi đối chiếu.')
    result = compare_sources(contract_repository.version_sources(left), contract_repository.version_sources(right))
    result.update(left_version_id=left.pk, right_version_id=right.pk)
    return result


def available_versions(user):
    versions, total = contract_repository.latest_visible_versions(user)
    return dict(success=True, versions=[dict(id=v.pk, title=v.contract.title, contract_id=v.contract_id,
        version_number=v.version_number) for v in versions if contract_repository.completed_extraction_run(v)],
        latest_versions_only=True, partial=total > 100)


def discovered_warnings(sources, version_ids, partial=False):
    """Automatic checks within the already-authorized A2 discovery shortlist."""
    ids = list(dict.fromkeys(version_ids))[:6]
    if partial:
        return dict(status='not_checked_incomplete_sources', warnings=[], documents_checked=0)
    grouped = {identity: [r for r in sources if r.get('version_id') == identity] for identity in ids}
    warnings = []
    for index, left in enumerate(ids):
        for right in ids[index+1:]:
            result = compare_sources(grouped[left], grouped[right])
            if result['differences'] or result['duplicate']['status'] in {'same_extracted_text', 'similar_text_review_required'}:
                warnings.append(dict(left_version_id=left, right_version_id=right,
                    left_title=grouped[left][0].get('original_name', '') if grouped[left] else '',
                    right_title=grouped[right][0].get('original_name', '') if grouped[right] else '',
                    differences=result['differences'], duplicate=result['duplicate']))
    return dict(status='checked_discovered_documents', warnings=warnings[:5],
                documents_checked=len(ids), partial=len(warnings) > 5,
                whole_collection_checked=False)
