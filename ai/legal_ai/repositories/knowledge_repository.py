"""Database access for search receipts and audit records."""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Q
from ai.ai_extract.models import LegalDocument
from contract.contracts.models import KnowledgeSearchLog, AuditLog


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


def update_legal(document, **fields):
    """The details a user set on a marked document; the other fields (source, kind) stay as they were."""
    for name, value in fields.items():
        setattr(document, name, value)
    document.save(update_fields=list(fields))
    return document


def legal_applied(document):
    """Whether search and risk analysis read this text now (the same rule as contract_repository.legal_contracts)."""
    from datetime import date
    if document.status in (*LegalDocument.IN_FORCE, LegalDocument.UPLOADED):
        return True
    return document.status == LegalDocument.NOT_YET_IN_FORCE and bool(document.effective_on) \
        and document.effective_on <= date.today()


def switch_legal(document, on):
    """Turn a legal text off (kept in store, never read as law) or on again (back to the status it had before).
    Answers whether anything changed: a text already off, or one that was not turned off, is left as it is."""
    off_now = document.status == LegalDocument.REPEALED
    if on != off_now:
        return False
    if on:
        update_legal(document, status=document.status_before_off or LegalDocument.FULLY_IN_FORCE, status_before_off='')
    else:
        update_legal(document, status=LegalDocument.REPEALED, status_before_off=document.status)
    return True


def legal_documents_for_admin(user):
    """The legal texts an administrator sees: all of them for the system administrator, otherwise the public ones and
    the company's own."""
    rows = LegalDocument.objects.select_related('contract').order_by('pk')
    if user.is_superuser:
        return list(rows)
    return list(rows.filter(Q(public=True) | Q(contract__company_id=user.company_id)) if user.company_id
                else rows.filter(public=True))


def legal_document_by_id(document_id):
    return LegalDocument.objects.select_related('contract').filter(pk=document_id).first()


def unmark_legal(contract):
    LegalDocument.objects.filter(contract=contract).delete()
