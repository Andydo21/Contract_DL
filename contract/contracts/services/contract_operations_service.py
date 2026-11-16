from contract.contracts.repositories import contract_operations_data_repository as data_repository
from contract.contracts.services.contract_service import ContractService
from contract.core.services.results import ServiceResult
from contract.core.services.access_service import check_contract_permission as _check_contract_permission
from contract.core.services.access_service import contract_access_error, is_manager
import logging
logger = logging.getLogger(__name__)
contract_service = ContractService()

def contract_detail_page(contract_id, user, query):
    """Render Contract Detail standalone UI Page (contract_detail.html)."""
    from contract.contracts.models import Contract
    try:
        contract_obj = data_repository.get_contract_for_contract_detail(contract_id)
        if not _check_contract_permission(user, contract_obj):
            return ServiceResult({}, template='contracts/access_denied.html')
    except Contract.DoesNotExist:
        return ServiceResult({}, status=404, template='common/not_found.html')
    version_id = query.get('version_id')
    details = contract_service.get_contract_details(contract_id, version_id=version_id)
    if not details:
        return ServiceResult({}, status=404, template='common/not_found.html')
    return ServiceResult({'contract': details}, template='contracts/contract_detail.html')

def contract_detail(contract_id, user, method, query):
    """
    GET: Get full detail of a contract.
    """
    if method == 'GET':
        from contract.contracts.models import Contract
        try:
            contract_obj = data_repository.get_contract_for_contract_detail(contract_id)
            if not _check_contract_permission(user, contract_obj):
                return ServiceResult({'error': 'Permission Denied: You do not have access to this contract.'}, status=403)
        except Contract.DoesNotExist:
            return ServiceResult({'error': 'Contract not found.'}, status=404)
        version_id = query.get('version_id')
        details = contract_service.get_contract_details(contract_id, version_id=version_id)
        if not details:
            return ServiceResult({'error': 'Contract not found.'}, status=404)
        return ServiceResult(details)
    if method == 'DELETE':
        return delete_contract(contract_id, user)
    return ServiceResult({'error': 'Method not allowed.'}, status=405)


def _delete_blocker(contract):
    """Why the contract cannot be deleted right now, or None. Only ledger work the worker has not finished postpones a
    deletion; an extraction or analysis running in the background is cancelled for this contract instead."""
    if data_repository.ledger_in_flight_for_delete(contract):
        return 'Có giao dịch blockchain của hợp đồng đang được gửi/ghi sổ; hãy chờ worker hoàn tất rồi xoá.'
    return None


def _remove_stored_files(files, pages):
    """Uploaded files and page images; a file already gone is not an error."""
    from contract.core.services.stored_file_service import physical_path
    removed = 0
    for stored in list(files) + list(pages):
        path = physical_path(stored)
        try:
            if path and path.is_file():
                path.unlink()
                removed += 1
        except OSError:
            logger.warning('Could not remove stored file %s', stored, exc_info=True)
    return removed


def delete_contract(contract_id, user):
    """DELETE: remove a contract with its versions, files, extraction, analyses, graph and vectors."""
    import json
    from contract.contracts.models import Contract
    if not is_manager(user):
        return ServiceResult({'error': 'Permission Denied: Only Managers can delete contracts.'}, status=403)
    try:
        contract = data_repository.get_contract_for_contract_detail(contract_id)
    except Contract.DoesNotExist:
        return ServiceResult({'error': 'Contract not found.'}, status=404)
    if not _check_contract_permission(user, contract):
        return ServiceResult({'error': 'Permission Denied: You do not have access to this contract.'}, status=403)
    blocker = _delete_blocker(contract)
    if blocker:
        return ServiceResult({'error': blocker, 'code': 'delete_blocked'}, status=409)
    from ai.ai_extract.services import layout_service
    from ai.ai_extract.services.bulk_service import cancel_contract
    # Background work on this contract stops here; a job extracting it right now cleans up its own output after.
    extracting = cancel_contract(contract.pk)
    try:
        index = layout_service.purge_contract_index(contract)
    except Exception as error:
        logger.exception('Index purge failed for contract %s', contract.pk)
        return ServiceResult({'error': f'Không xoá được dữ liệu chỉ mục (đồ thị/vector): {error}'}, status=502)
    from contract.approvals.services.workflow_service import WorkflowService
    versions = data_repository.version_ids_for_delete(contract)
    try:
        workflows = WorkflowService().delete_workflows(versions)
    except RuntimeError as error:
        return ServiceResult({'error': f'Không xoá được quy trình duyệt: {error}'}, status=502)
    files, pages = data_repository.stored_paths_for_delete(contract)
    payload = json.dumps(dict(contract_id=contract.pk, contract_code=contract.contract_code, title=contract.title,
                              company_id=contract.company_id, versions=versions, index=index, workflows=workflows,
                              dependents=data_repository.dependents_for_delete(contract),
                              ledger_evidence=data_repository.ledger_evidence_for_delete(contract)),
                         ensure_ascii=False, default=str)
    data_repository.delete_contract_records(contract, user, payload)
    removed = _remove_stored_files(files, pages)
    return ServiceResult({'success': True, 'contract_id': int(contract_id), 'removed_files': removed, 'index': index,
                          'workflows_deleted': workflows, 'background_extraction_cancelled': extracting})


def contracts_list(user, method, form=None, uploads=None):
    """
    GET: Get list of all contracts.
    """
    if method == 'GET':
        try:
            if not user.is_superuser and not user.company_id:
                return ServiceResult([])
            company = None if user.is_superuser else user.company
            contracts = contract_service.list_all_contracts(company=company)
            return ServiceResult(contracts)
        except Exception as e:
            return ServiceResult({'error': str(e)}, status=500)
    elif method == 'POST':
        if not is_manager(user):
            return ServiceResult({'error': 'Permission Denied: Only Managers can create contracts.'}, status=403)
        return create_contract(user, method, form or {}, uploads or {})
    return ServiceResult({'error': 'Method not allowed.'}, status=405)

def _extract_after_upload(user, contract_id):
    """An uploaded document starts extracting at once, in the background job queue."""
    from ai.ai_extract.services.bulk_service import extract_after_upload
    try:
        return extract_after_upload(user, contract_id)
    except Exception:
        logger.exception('Could not queue extraction of contract %s', contract_id)
        return None

def create_contract(user, method, form, uploads):
    """
    POST: Create a contract with its uploaded file or pasted text; extraction starts in the background.
    """
    if method != 'POST':
        return ServiceResult({'error': 'Method not allowed.'}, status=405)
    code = form.get('contract_code')
    title = form.get('title')
    contract_type = form.get('contract_type', '')
    start_date = form.get('start_date') or None
    end_date = form.get('end_date') or None
    contract_value = form.get('contract_value') or '0.00'
    raw_content = form.get('raw_content')
    if not code or not title:
        return ServiceResult({'error': 'Contract code and title are required.'}, status=400)
    from contract.contracts.services.page_images_service import PageImagesError, document_upload
    try:
        file_obj = document_upload(uploads)
    except PageImagesError as error:
        return ServiceResult({'error': str(error)}, status=400)
    if not file_obj and not (raw_content or '').strip():
        return ServiceResult({'error': 'Cần tải tệp hợp đồng hoặc dán nội dung hợp đồng.'}, status=400)
    try:
        company = None
        if user.is_authenticated:
            company = getattr(user, 'company', None)
        contract = contract_service.create_and_analyze_contract(code=code, title=title, contract_type=contract_type, start_date=start_date, end_date=end_date, contract_value=contract_value, file_obj=file_obj, raw_content=raw_content, company=company)
        if form.get('document_kind') == 'legal':
            from ai.legal_ai.repositories.knowledge_repository import mark_legal
            mark_legal(contract)
        job = _extract_after_upload(user, contract.id) if file_obj or raw_content else None
        return ServiceResult({'success': True, 'contract_id': contract.id, 'contract_code': contract.contract_code, 'status': contract.status,
                              'extraction_job_id': job and job['id']})
    except Exception as e:
        return ServiceResult({'error': str(e)}, status=400)

def contract_versions(contract_id, user, method, form, uploads):
    """
    GET: Get all versions of a contract.
    POST: Create a new version of the contract; its extraction starts in the background.
    """
    access_error = contract_access_error(user, contract_id)
    if access_error:
        return access_error
    if method == 'POST' and not is_manager(user):
        return ServiceResult({'error': 'Manager role required.'}, status=403)
    if method == 'GET':
        details = contract_service.get_contract_details(contract_id)
        if not details:
            return ServiceResult({'error': 'Contract not found.'}, status=404)
        return ServiceResult({'versions': details.get('versions', [])})
    elif method == 'POST':
        change_summary = form.get('change_summary', '')
        raw_content = form.get('raw_content')
        from contract.contracts.services.page_images_service import PageImagesError, document_upload
        try:
            file_obj = document_upload(uploads)
        except PageImagesError as error:
            return ServiceResult({'error': str(error)}, status=400)
        if not file_obj and (not raw_content):
            return ServiceResult({'error': 'Either a file or text content is required for the new version.'}, status=400)
        try:
            version = contract_service.create_new_version(contract_id=contract_id, file_obj=file_obj, raw_content=raw_content, change_summary=change_summary)
            job = _extract_after_upload(user, int(contract_id))
            return ServiceResult({'success': True, 'version_id': version.id, 'version_number': version.version_number, 'change_summary': version.change_summary,
                                  'extraction_job_id': job and job['id']})
        except Exception as e:
            return ServiceResult({'error': str(e)}, status=400)
    return ServiceResult({'error': 'Method not allowed.'}, status=405)
