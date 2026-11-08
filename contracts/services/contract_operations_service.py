from contracts.repositories import contract_operations_data_repository as data_repository
from contracts.services import ContractService
from contracts.services.results import ServiceResult
from contracts.services.access_service import check_contract_permission as _check_contract_permission
from contracts.services.access_service import contract_access_error
import logging
logger = logging.getLogger(__name__)
contract_service = ContractService()

def contract_detail_page(contract_id, user, query):
    """Render Contract Detail standalone UI Page (contract_detail.html)."""
    from contracts.models import Contract
    try:
        contract_obj = data_repository.get_contract_for_contract_detail(contract_id)
        if not _check_contract_permission(user, contract_obj):
            return ServiceResult({}, template='contracts/access_denied.html')
    except Contract.DoesNotExist:
        return ServiceResult({}, template='404.html')
    version_id = query.get('version_id')
    details = contract_service.get_contract_details(contract_id, version_id=version_id)
    if not details:
        return ServiceResult({}, template='404.html')
    return ServiceResult({'contract': details}, template='contracts/contract_detail.html')

def contract_detail(contract_id, user, method, query):
    """
    GET: Get full detail of a contract.
    """
    if method == 'GET':
        from contracts.models import Contract
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
    return ServiceResult({'error': 'Method not allowed.'}, status=405)

def contracts_list(user, method, form=None, uploads=None):
    """
    GET: Get list of all contracts.
    """
    if method == 'GET':
        try:
            user = user
            is_manager = user.is_superuser or (user.role and user.role.role_name.upper() in ['MANAGER', 'ADMIN'])
            if not user.is_superuser and not user.company_id:
                return ServiceResult([])
            company = None if user.is_superuser else user.company
            contracts = contract_service.list_all_contracts(company=company)
            return ServiceResult(contracts)
        except Exception as e:
            return ServiceResult({'error': str(e)}, status=500)
    elif method == 'POST':
        user = user
        is_manager = user.is_superuser or (user.role and user.role.role_name.upper() in ['MANAGER', 'ADMIN'])
        if not is_manager:
            return ServiceResult({'error': 'Permission Denied: Only Managers can create contracts.'}, status=403)
        return create_contract(user, method, form or {}, uploads or {})
    return ServiceResult({'error': 'Method not allowed.'}, status=405)

def _extract_after_upload(user, contract_id):
    """An uploaded document starts extracting at once, in the background job queue."""
    from ai_extract.services.bulk_service import extract_after_upload
    try:
        return extract_after_upload(user, contract_id)
    except Exception:
        logger.exception('Could not queue extraction of contract %s', contract_id)
        return None

def create_contract(user, method, form, uploads):
    """
    POST: Create a contract, upload file/text, and trigger mock AI Analysis.
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
    from contracts.services.page_images_service import PageImagesError, document_upload
    try:
        file_obj = document_upload(uploads)
    except PageImagesError as error:
        return ServiceResult({'error': str(error)}, status=400)
    try:
        company = None
        if user.is_authenticated:
            company = getattr(user, 'company', None)
        contract = contract_service.create_and_analyze_contract(code=code, title=title, contract_type=contract_type, start_date=start_date, end_date=end_date, contract_value=contract_value, file_obj=file_obj, raw_content=raw_content, company=company)
        if form.get('document_kind') == 'legal':
            from NewIdea.repositories.knowledge_repository import mark_legal
            mark_legal(contract)
        job = _extract_after_upload(user, contract.id) if file_obj or raw_content else None
        return ServiceResult({'success': True, 'contract_id': contract.id, 'contract_code': contract.contract_code, 'status': contract.status,
                              'extraction_job_id': job and job['id']})
    except Exception as e:
        return ServiceResult({'error': str(e)}, status=400)

def manual_extract_contract(contract_id, user, method, data, form, query):
    """
    POST: Extract the document again through the main pipeline, as a background job (run by the AI service when
    there is one); the contract page follows it on its extraction progress bar.
    """
    if method == 'POST':
        version_id = query.get('version_id') or form.get('version_id')
        if not version_id and data:
            try:
                body = data
                version_id = body.get('version_id')
            except Exception:
                pass
        try:
            contract_obj = data_repository.get_contract_for_contract_detail(contract_id)
            if not _check_contract_permission(user, contract_obj):
                return ServiceResult({'error': 'Permission Denied.'}, status=403)
            if version_id and str(version_id) != str(getattr(contract_obj.latest_version, 'pk', '')):
                return ServiceResult({'error': 'Chỉ trích xuất lại được phiên bản mới nhất.'}, status=400)
            from django.core.exceptions import PermissionDenied
            from ai_extract.services.bulk_service import start
            try:
                job = start(user, [contract_obj.pk], 'extract')
            except PermissionDenied as denied:
                return ServiceResult({'error': str(denied)}, status=403)
            return ServiceResult({'success': True, 'queued': True, 'job_id': job['id'], 'contract_id': contract_obj.pk})
        except Exception as e:
            return ServiceResult({'error': str(e)}, status=400)
    return ServiceResult({'error': 'Method not allowed.'}, status=405)

def contract_versions(contract_id, user, method, form, uploads):
    """
    GET: Get all versions of a contract.
    POST: Create a new version of the contract, parse clauses, and auto-run AI analysis.
    """
    access_error = contract_access_error(user, contract_id)
    if access_error:
        return access_error
    if method == 'POST' and not (user.is_superuser or user.role and user.role.role_name.upper() in ('MANAGER', 'ADMIN')):
        return ServiceResult({'error': 'Manager role required.'}, status=403)
    if method == 'GET':
        details = contract_service.get_contract_details(contract_id)
        if not details:
            return ServiceResult({'error': 'Contract not found.'}, status=404)
        return ServiceResult({'versions': details.get('versions', [])})
    elif method == 'POST':
        change_summary = form.get('change_summary', '')
        raw_content = form.get('raw_content')
        from contracts.services.page_images_service import PageImagesError, document_upload
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
