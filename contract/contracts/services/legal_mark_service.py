"""The user marks a stored document as a legal text and sets its details (number, status, date it takes effect);
nothing is guessed. A text marked "Hết hiệu lực" stays stored but is never used as law, and one not yet in force is
used from its date on. Marking or unmarking extracts the document again, so its articles are read as law (or not)."""
from datetime import date

from ai.ai_extract.models import LegalDocument
from contract.contracts.repositories.contract_repository import ContractRepository
from contract.core.services.access_service import contract_access_error, is_manager
from contract.core.services.results import ServiceResult
from ai.legal_ai.repositories import knowledge_repository

STATUSES = (LegalDocument.FULLY_IN_FORCE, LegalDocument.PARTLY_REPEALED, LegalDocument.NOT_YET_IN_FORCE,
            LegalDocument.REPEALED, LegalDocument.UPLOADED)
MARKED_BY_USER = 'Người dùng đánh dấu'


def serialize(document):
    if document is None:
        return None
    return dict(number=document.number, title=document.title, status=document.status,
                effective_on=document.effective_on.isoformat() if document.effective_on else '')


def _extract_again(user, contract):
    from ai.ai_extract.services.bulk_service import extract_after_upload
    try:
        job = extract_after_upload(user, contract.pk)
    except Exception:
        return None
    return job and job['id']


def contract_legal(contract_id, user, method, data):
    error = contract_access_error(user, contract_id)
    if error:
        return error
    contract = ContractRepository.get_contract_by_id(contract_id)
    document = knowledge_repository.legal_document_for(contract)
    if method == 'GET':
        return ServiceResult({'legal': serialize(document), 'statuses': list(STATUSES)})
    if method != 'POST':
        return ServiceResult({'error': 'Method not allowed.'}, status=405)
    if not is_manager(user):
        return ServiceResult({'error': 'Chỉ quản lý được đánh dấu văn bản pháp luật.'}, status=403)
    data = data if isinstance(data, dict) else {}
    if not data.get('is_legal'):
        if document is None:
            return ServiceResult({'success': True, 'legal': None})
        knowledge_repository.unmark_legal(contract)
        return ServiceResult({'success': True, 'legal': None, 'extraction_job_id': _extract_again(user, contract)})
    status = data.get('status') or LegalDocument.UPLOADED
    if status not in STATUSES:
        return ServiceResult({'error': f'Tình trạng phải là một trong: {", ".join(STATUSES)}.'}, status=400)
    effective_on = None
    if data.get('effective_on'):
        try:
            effective_on = date.fromisoformat(str(data['effective_on']))
        except ValueError:
            return ServiceResult({'error': 'Ngày có hiệu lực không hợp lệ (định dạng YYYY-MM-DD).'}, status=400)
    if status == LegalDocument.NOT_YET_IN_FORCE and effective_on is None:
        return ServiceResult({'error': 'Văn bản chưa có hiệu lực cần ngày có hiệu lực.'}, status=400)
    details = dict(number=' '.join(str(data.get('number') or '').split())[:120] or contract.contract_code,
                   title=' '.join(str(data.get('title') or '').split()) or contract.title,
                   status=status, effective_on=effective_on, text_source=MARKED_BY_USER)
    job = None
    if document is None:
        document = knowledge_repository.mark_legal(contract, **details)
        job = _extract_again(user, contract)
    else:
        document = knowledge_repository.update_legal(document, **details)
    return ServiceResult({'success': True, 'legal': serialize(document), 'extraction_job_id': job})
