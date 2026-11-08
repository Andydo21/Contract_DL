"""Parties of a contract, entered by the user (the AI does not guess them), and tags from the administrator's list."""
from contracts.repositories import party_tag_repository as repository
from contracts.services.access_service import contract_access_error
from contracts.services.results import ServiceResult

PARTY_TYPES = ('Bên A', 'Bên B', 'Bên khác')
FIELDS = ('party_name', 'party_type', 'tax_code', 'email', 'phone')


def serialize_party(party):
    return {field: getattr(party, field) or '' for field in FIELDS} | dict(id=party.pk)


def contract_parties(contract_id, user, method, data):
    from contracts.repositories import ContractRepository
    error = contract_access_error(user, contract_id)
    if error:
        return error
    contract = ContractRepository.get_contract_by_id(contract_id)
    if method == 'GET':
        return ServiceResult({'parties': [serialize_party(p) for p in repository.parties_of(contract)]})
    if method != 'POST':
        return ServiceResult({'error': 'Method not allowed.'}, status=405)
    rows = data.get('parties') if isinstance(data, dict) else None
    if not isinstance(rows, list) or len(rows) > 10:
        return ServiceResult({'error': 'parties phải là danh sách tối đa 10 bên.'}, status=400)
    cleaned = []
    for row in rows:
        if not isinstance(row, dict):
            return ServiceResult({'error': 'Mỗi bên phải là một đối tượng.'}, status=400)
        name = ' '.join(str(row.get('party_name') or '').split())
        kind = row.get('party_type')
        if not name:
            continue
        if kind not in PARTY_TYPES:
            return ServiceResult({'error': f'Vai trò phải là một trong: {", ".join(PARTY_TYPES)}.'}, status=400)
        cleaned.append(dict(party_name=name[:255], party_type=kind, tax_code=str(row.get('tax_code') or '').strip()[:100] or None,
                            email=str(row.get('email') or '').strip()[:254] or None, phone=str(row.get('phone') or '').strip()[:50] or None))
    saved = repository.replace_parties(contract, cleaned)
    return ServiceResult({'success': True, 'parties': [serialize_party(p) for p in saved]})


def contract_tags(contract_id, user, method, data):
    from contracts.repositories import ContractRepository
    error = contract_access_error(user, contract_id)
    if error:
        return error
    contract = ContractRepository.get_contract_by_id(contract_id)
    if method == 'POST':
        ids = data.get('tag_ids') if isinstance(data, dict) else None
        if not isinstance(ids, list) or any(type(i) is not int for i in ids):
            return ServiceResult({'error': 'tag_ids phải là danh sách số.'}, status=400)
        repository.set_tags(contract, ids)
    elif method != 'GET':
        return ServiceResult({'error': 'Method not allowed.'}, status=405)
    chosen = {t.pk for t in repository.tags_of(contract)}
    return ServiceResult({'success': True, 'tags': [dict(id=t.pk, name=t.tag_name, selected=t.pk in chosen) for t in repository.all_tags()]})
