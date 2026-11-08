"""Database access for search receipts, expert inquiries, cases and audit records."""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Q
from ai_extract.models import LegalDocument
from contracts.models import ContractKnowledgeCase, ContractKnowledgeInquiry, KnowledgeSearchLog, AuditLog


def lock_user(user):
    return get_user_model().objects.select_for_update().get(pk=user.pk)


STALE_SEARCH_AFTER = timedelta(minutes=30)


def search_quota(user):
    recent = KnowledgeSearchLog.objects.filter(user=user, created_at__gte=timezone.now()-timedelta(minutes=1))
    # A search whose process was killed (a container restart) stays RUNNING forever; three of them blocked
    # every later question of that user. No search runs this long: one Qwen call is capped at 10 minutes.
    pending = KnowledgeSearchLog.objects.filter(user=user, generated=True, status__in=['QUEUED', 'RUNNING', 'FINALIZING'],
                                                created_at__gte=timezone.now()-STALE_SEARCH_AFTER).count()
    return recent.count(), recent.filter(generated=True).count(), pending


def create_search(user, query, version, generated, scope):
    return KnowledgeSearchLog.objects.create(user=user, version=version, query=query, generated=generated, scope=scope)


def save_search(log, *fields):
    log.save(update_fields=list(fields))


def get_visible_search(user, search_id, completed_own=False):
    from .contract_repository import visible_contracts
    company_scope = Q(user=user, scope='company', version__isnull=True) & (
        Q(result__coverage__company_id=user.company_id) | Q(result__request__company_id=user.company_id))
    company_scope |= Q(user=user, scope='expert', result__request__company_id=user.company_id)
    if not user.company_id:
        company_scope = Q(pk__in=[])
    knowledge_scope = Q(user=user, scope='knowledge', version__isnull=True,
        result__access__company_id=user.company_id, result__access__is_superuser=user.is_superuser)
    records = KnowledgeSearchLog.objects.filter(Q(version__contract__in=visible_contracts(user)) | company_scope | knowledge_scope)
    if completed_own:
        records = records.filter(user=user, status='COMPLETED')
    return records.get(pk=search_id)


def visible_inquiries(user, own_only=False):
    from .contract_repository import visible_contracts
    records = ContractKnowledgeInquiry.objects.filter(version__contract__in=visible_contracts(user)).select_related('version__contract', 'requester', 'assignee', 'case', 'search')
    return records.filter(requester=user) if own_only else records


def get_visible_inquiry(user, inquiry_id, own_only=False, lock=False):
    records = visible_inquiries(user, own_only)
    if lock:
        records = records.select_for_update(of=('self',))
    return records.get(pk=inquiry_id)


def active_reviewers(company_id):
    return get_user_model().objects.filter(is_active=True, company_id=company_id, role__role_name__in=['MANAGER', 'ADMIN']) if company_id else get_user_model().objects.none()


def get_active_assignee(company_id, user_id):
    return get_user_model().objects.get(pk=user_id, is_active=True, company_id=company_id)


def create_inquiry(receipt, user):
    return ContractKnowledgeInquiry.objects.get_or_create(search=receipt,
        defaults=dict(version=receipt.version, requester=user, question=receipt.query))


def new_case(version, author):
    return ContractKnowledgeCase(version=version, author=author)


def save_case(case):
    case.save()


def enqueue_case_index(case, user):
    """Index after commit in the existing worker, keeping HTTP writes fast."""
    from django.db import transaction
    if case.status == 'approved':
        transaction.on_commit(lambda: KnowledgeSearchLog.objects.create(user=user, scope='knowledge_index',
            query='Index expert case', status='QUEUED', generated=False,
            result=dict(request=dict(scope='knowledge_index', knowledge_key=f'A2:{case.case_id}:r{case.revision}'))))


def save_inquiry(inquiry):
    inquiry.save()


def record_inquiry_action(user, inquiry, action, payload):
    AuditLog.objects.create(user=user, contract=inquiry.version.contract,
        action='A2_INQUIRY_'+action.upper(), payload=payload)


def inquiry_list(user, own_only=False):
    return list(visible_inquiries(user, own_only).order_by('-updated_at')[:100])


def reviewer_list(company_id):
    return list(active_reviewers(company_id).values('id', 'username'))


def next_queued_search():
    from django.db import connection
    jobs = KnowledgeSearchLog.objects.filter(status='QUEUED').order_by('created_at')
    jobs = jobs.select_for_update(skip_locked=True) if connection.features.has_select_for_update_skip_locked else jobs.select_for_update()
    return jobs.first()


def fail_stale_searches():
    return KnowledgeSearchLog.objects.filter(status__in=['RUNNING','FINALIZING'], generated=True,
        created_at__lt=timezone.now()-timedelta(hours=2)).update(status='FAILED')


def legal_note(document):
    if document.status == LegalDocument.UPLOADED:
        return 'Tài liệu do người dùng tải lên; hiệu lực chưa được xác minh.'
    notes = []
    if document.doc_type == LegalDocument.TRANSLATION:
        notes.append('Đây là bản dịch tham khảo, không thay thế văn bản gốc tiếng Việt.')
    if document.status != LegalDocument.FULLY_IN_FORCE:
        notes.append(f'Tình trạng: {document.status}. Các điều của văn bản này có thể không còn áp dụng nguyên văn.')
    if document.amended_by:
        notes.append('Đã được sửa đổi hoặc bổ sung bởi: '+', '.join(document.amended_by)+'.')
    return ' '.join(notes)


def legal_fields(versions):
    """What each legal source must state about its document, by version id."""
    rows = LegalDocument.objects.filter(contract__versions__in=versions).values_list('contract__versions__pk', 'pk')
    documents = LegalDocument.objects.in_bulk({pk for _, pk in rows})
    return {version: dict(evidence_kind='legal_provision', legal_number=documents[pk].number, legal_type=documents[pk].doc_type,
                          legal_status=documents[pk].status,
                          legal_note=legal_note(documents[pk]))
            for version, pk in rows}


def legal_document_for(contract):
    return LegalDocument.objects.filter(contract=contract).first()


def mark_legal(contract, **fields):
    """The row is the mark. Without published details the document counts as an unverified upload."""
    document, _ = LegalDocument.objects.update_or_create(contract=contract, defaults=dict(dict(
        source_id=f'contract:{contract.pk}', number=contract.contract_code, title=contract.title,
        doc_type=LegalDocument.UPLOADED_TYPE, status=LegalDocument.UPLOADED), **fields))
    return document


def unmark_legal(contract):
    LegalDocument.objects.filter(contract=contract).delete()
