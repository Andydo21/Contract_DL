"""A2 domain rules used by the main Contract Guard web application."""
import re
import unicodedata

CASE_FIELDS = ('title', 'clause_type', 'issue', 'reasoning', 'resolution',
               'verification', 'applicability', 'source_reference')


def normalized(value):
    return unicodedata.normalize('NFC', str(value)).casefold().strip()


def overlap(query, text):
    query_terms = set(re.findall(r'[^\W_]+(?:[-./][^\W_]+)*', normalized(query)))
    terms = set(re.findall(r'[^\W_]+(?:[-./][^\W_]+)*', normalized(text)))
    return len(query_terms & terms) / len(query_terms) if query_terms else 0


def approval_gaps(case):
    return [name for name in ('issue', 'reasoning', 'resolution', 'verification',
                             'applicability', 'source_reference')
            if not getattr(case, name, '').strip()]

def can_review(user):
    return user.is_superuser or bool(user.role and user.role.role_name.upper() in {'MANAGER', 'ADMIN'})


def serialize_case(case):
    contract = case.version.contract
    return dict({f: getattr(case, f) for f in CASE_FIELDS}, id=case.pk,
        case_id=str(case.case_id), revision=case.revision, status=case.status,
        contract_id=contract.pk, contract_code=contract.contract_code,
        contract_type=contract.contract_type or '', version_id=case.version_id,
        version_number=case.version.version_number,
        author=case.author.username, reviewer=case.reviewer.username if case.reviewer else None,
        is_demo=case.title.startswith('[DEMO]'),
        evidence_snapshot=case.evidence_snapshot,
        evidence_id=f'A2:{case.case_id}:r{case.revision}')


