from django.db import IntegrityError, transaction
from contracts.repositories import contract_operations_data_repository as data_repository
from contracts.services import ContractService
from contracts.services.results import ServiceResult
from contracts.services.access_service import check_contract_permission as _check_contract_permission
from contracts.services.access_service import contract_access_error
import logging
logger = logging.getLogger(__name__)
contract_service = ContractService()

def summarize_choice(form):
    """The upload form's "summarize right away" checkbox; None when the field was not sent (use the default)."""
    value = form.get('summarize')
    return None if value is None else value.lower() in ('1', 'true', 'on', 'yes')

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

def _is_manager(user):
    return bool(user.is_superuser or (user.role and user.role.role_name.upper() in ('MANAGER', 'ADMIN')))

EDITABLE_FIELDS = ('contract_code', 'title', 'contract_type', 'start_date', 'end_date', 'contract_value')

def _clean_contract_fields(data, contract):
    """The metadata a manager may change; status, company and versions have their own flows."""
    from datetime import date
    from decimal import Decimal, InvalidOperation
    unknown = sorted(set(data) - set(EDITABLE_FIELDS))
    if unknown:
        raise ValueError('Không sửa được các trường: ' + ', '.join(unknown))
    fields = {}
    for name in ('contract_code', 'title'):
        if name in data:
            value = str(data[name] or '').strip()
            if not value:
                raise ValueError('Mã hợp đồng và tiêu đề không được để trống.')
            limit = contract._meta.get_field(name).max_length
            if len(value) > limit:
                raise ValueError(f'{name} dài quá {limit} ký tự.')
            fields[name] = value
    if 'contract_type' in data:
        value = str(data['contract_type'] or '').strip()
        if len(value) > 100:
            raise ValueError('contract_type dài quá 100 ký tự.')
        fields['contract_type'] = value
    for name in ('start_date', 'end_date'):
        if name in data:
            value = data[name]
            if value in (None, ''):
                fields[name] = None
            else:
                try:
                    fields[name] = date.fromisoformat(str(value))
                except ValueError:
                    raise ValueError(f'{name} phải có dạng YYYY-MM-DD.')
    if 'contract_value' in data:
        value = data['contract_value']
        if value in (None, ''):
            fields['contract_value'] = None
        else:
            try:
                amount = Decimal(str(value))
            except InvalidOperation:
                raise ValueError('Giá trị hợp đồng phải là số.')
            if not amount.is_finite() or amount < 0:
                raise ValueError('Giá trị hợp đồng phải là số không âm.')
            column = contract._meta.get_field('contract_value')
            limit = Decimal(10) ** (column.max_digits - column.decimal_places)
            if amount < limit:
                amount = amount.quantize(Decimal('0.01'))
            if amount >= limit:  # also after rounding: 9999999999999999.999 rounds up to one digit too many
                raise ValueError(f'Giá trị hợp đồng quá lớn (tối đa {column.max_digits - column.decimal_places} chữ số phần nguyên).')
            fields['contract_value'] = amount
    start = fields.get('start_date', contract.start_date)
    end = fields.get('end_date', contract.end_date)
    if start and end and end < start:
        raise ValueError('Ngày kết thúc phải sau ngày bắt đầu.')
    return fields

def _managed_contract(contract_id, user):
    """The contract a manager of its company may change, or the error result to return."""
    from contracts.models import Contract
    if not _is_manager(user):
        return None, ServiceResult({'error': 'Permission Denied: Only Managers can change contracts.'}, status=403)
    try:
        contract = data_repository.get_contract_for_contract_detail(contract_id)
    except Contract.DoesNotExist:
        return None, ServiceResult({'error': 'Contract not found.'}, status=404)
    if not _check_contract_permission(user, contract):
        return None, ServiceResult({'error': 'Permission Denied: You do not have access to this contract.'}, status=403)
    return contract, None

def update_contract(contract_id, user, data):
    """PATCH/PUT: change a contract's metadata (code, title, type, dates, value)."""
    import json
    from contracts.repositories import ContractRepository
    contract, error = _managed_contract(contract_id, user)
    if error:
        return error
    fields = _clean_contract_fields(data or {}, contract)
    changed = {name: value for name, value in fields.items() if getattr(contract, name) != value}
    if not changed:
        return ServiceResult({'success': True, 'contract_id': contract.id, 'changed': []})
    diff = {name: [str(getattr(contract, name)) if getattr(contract, name) is not None else None, str(value) if value is not None else None]
            for name, value in changed.items()}
    # The change and its audit row are saved together or not at all.
    with transaction.atomic():
        try:
            with transaction.atomic():
                ContractRepository.update_contract(contract, changed)
        except IntegrityError:
            return ServiceResult({'error': f'Mã hợp đồng "{changed.get("contract_code")}" đã tồn tại. Hãy dùng mã khác.'}, status=400)
        data_repository.log_contract_action(user, contract, f'Updated contract: {contract.contract_code}', json.dumps(diff, ensure_ascii=False))
    return ServiceResult({'success': True, 'contract_id': contract.id, 'changed': sorted(changed),
                          'contract': contract_service.contract_summary(contract)})

def delete_contract(contract_id, user):
    """DELETE: soft delete. The contract leaves every listing; its versions, files, ledger and audit history stay."""
    from contracts.repositories import ContractRepository
    contract, error = _managed_contract(contract_id, user)
    if error:
        return error
    if contract.status == 'ANALYZING':
        return ServiceResult({'error': 'Hợp đồng đang được phân tích. Hãy đợi phân tích xong rồi xóa.'}, status=409)
    from ai_extract.services.bulk_service import waiting_contract
    if waiting_contract(contract.pk):  # the job would fail half-way on a contract it can no longer find
        return ServiceResult({'error': 'Hợp đồng đang được trích xuất hoặc đang chờ xử lý. Hãy đợi xong rồi xóa.'}, status=409)
    with transaction.atomic():
        ContractRepository.soft_delete_contract(contract, user)
        data_repository.log_contract_action(user, contract, f'Deleted contract: {contract.contract_code}')
    return ServiceResult({'success': True, 'contract_id': contract.id, 'deleted_at': contract.deleted_at.isoformat()})

def deleted_contracts(user):
    """GET: the trash. What managers of the company deleted and can bring back."""
    from contracts.repositories import ContractRepository
    if not _is_manager(user):
        return ServiceResult({'error': 'Permission Denied: Only Managers can see deleted contracts.'}, status=403)
    if not user.is_superuser and not user.company_id:
        return ServiceResult({'contracts': []})
    rows = list(ContractRepository.deleted_contracts(None if user.is_superuser else user.company_id)[:200])
    in_use = ContractRepository.codes_in_use(row.contract_code for row in rows)
    return ServiceResult({'contracts': [dict(
        id=row.id, contract_code=row.contract_code, title=row.title, deleted_at=row.deleted_at.isoformat(),
        deleted_by=row.deleted_by.username if row.deleted_by else None,
        # Another contract took the code meanwhile: restoring needs a new one.
        code_taken=row.contract_code in in_use) for row in rows]})

def restore_contract(contract_id, user, data=None):
    """POST: bring a deleted contract back, under a new code when another contract uses its code now."""
    from contracts.models import Contract
    from contracts.repositories import ContractRepository
    if not _is_manager(user):
        return ServiceResult({'error': 'Permission Denied: Only Managers can restore contracts.'}, status=403)
    contract = ContractRepository.deleted_contract(contract_id)
    if contract is None:
        return ServiceResult({'error': 'Không tìm thấy hợp đồng đã xóa.'}, status=404)
    if not _check_contract_permission(user, contract):
        return ServiceResult({'error': 'Permission Denied: You do not have access to this contract.'}, status=403)
    new_code = _clean_contract_fields({'contract_code': (data or {})['contract_code']}, contract)['contract_code'] \
        if (data or {}).get('contract_code') else contract.contract_code
    old_code = contract.contract_code
    try:
        with transaction.atomic():
            if new_code != old_code:
                ContractRepository.update_contract(contract, {'contract_code': new_code})
            restored, _ = ContractRepository.restore_contracts(Contract.all_objects.filter(pk=contract.pk))
            if not restored:
                raise IntegrityError('code in use')
            note = f' (mã cũ {old_code})' if new_code != old_code else ''
            data_repository.log_contract_action(user, contract, f'Restored contract: {new_code}{note}')
    except IntegrityError:
        return ServiceResult({'error': f'Mã "{new_code}" đang được hợp đồng khác dùng. Hãy nhập mã mới để khôi phục.',
                              'code_taken': True}, status=409)
    return ServiceResult({'success': True, 'contract_id': contract.id, 'contract_code': new_code})

HISTORY_LABELS = (('Created contract', 'Tạo hợp đồng'), ('Updated contract', 'Sửa thông tin'), ('Deleted contract', 'Xóa hợp đồng'),
                  ('Restored contract', 'Khôi phục hợp đồng'), ('Added version', 'Thêm phiên bản'),
                  ('PUSHED_TO_WORKFLOW', 'Đưa vào quy trình phê duyệt'), ('Triggered AI analysis', 'Chạy phân tích rủi ro'),
                  ('Submitted expert review', 'Gửi đánh giá chuyên gia'))
FIELD_LABELS = dict(contract_code='Mã hợp đồng', title='Tiêu đề', contract_type='Loại hợp đồng', start_date='Ngày bắt đầu',
                    end_date='Ngày kết thúc', contract_value='Giá trị')

def contract_history(contract_id, user):
    """GET: who changed what on a contract, newest first, for everyone who may open it."""
    import json
    access_error = contract_access_error(user, contract_id)
    if access_error:
        return access_error
    history = []
    for row in data_repository.contract_history_rows(contract_id):
        label = next((text for prefix, text in HISTORY_LABELS if row.action.startswith(prefix)), row.action)
        detail = row.action.split(': ', 1)[1] if ': ' in row.action and label != row.action else ''
        changes = []
        if row.action.startswith('Updated contract') and row.payload:
            try:  # only this payload is a diff; other rows may carry a raw request body, which is never shown
                changes = [dict(field=name, label=FIELD_LABELS.get(name, name), before=before, after=after)
                           for name, (before, after) in json.loads(row.payload).items()]
            except (ValueError, TypeError):
                changes = []
        history.append(dict(at=row.created_at.isoformat(), user=row.user.username if row.user else None, label=label,
                            detail=detail, changes=changes))
    return ServiceResult({'history': history})

def contract_detail(contract_id, user, method, query, data=None):
    """
    GET: Get full detail of a contract.
    PATCH/PUT: Change its metadata (managers only).
    DELETE: Soft delete it (managers only).
    """
    if method in ('PATCH', 'PUT'):
        return update_contract(contract_id, user, data)
    if method == 'DELETE':
        return delete_contract(contract_id, user)
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
    from contracts.models import Contract
    raw_content = form.get('raw_content')
    if not form.get('contract_code') or not form.get('title'):
        return ServiceResult({'error': 'Cần nhập mã hợp đồng và tiêu đề.'}, status=400)
    # The same rules as an edit: no negative value, no end before the start, nothing longer than its column.
    try:
        fields = _clean_contract_fields({name: form.get(name) for name in EDITABLE_FIELDS if form.get(name) not in (None, '')}, Contract())
    except ValueError as error:
        return ServiceResult({'error': str(error)}, status=400)
    code, title = fields['contract_code'], fields['title']
    contract_type = fields.get('contract_type', '')
    start_date, end_date = fields.get('start_date'), fields.get('end_date')
    contract_value = fields.get('contract_value', '0.00')
    from contracts.services.page_images_service import PageImagesError, document_upload
    try:
        file_obj = document_upload(uploads)
    except PageImagesError as error:
        return ServiceResult({'error': str(error)}, status=400)
    try:
        company = None
        if user.is_authenticated:
            company = getattr(user, 'company', None)
        contract = contract_service.create_and_analyze_contract(code=code, title=title, contract_type=contract_type, start_date=start_date, end_date=end_date, contract_value=contract_value, file_obj=file_obj, raw_content=raw_content, company=company, summarize=summarize_choice(form))
        if form.get('document_kind') == 'legal':
            from NewIdea.repositories.knowledge_repository import mark_legal
            mark_legal(contract)
        data_repository.log_contract_action(user, contract, f'Created contract: {contract.contract_code}')
        job = _extract_after_upload(user, contract.id) if file_obj or raw_content else None
        return ServiceResult({'success': True, 'contract_id': contract.id, 'contract_code': contract.contract_code, 'status': contract.status,
                              'extraction_job_id': job and job['id']})
    except IntegrityError:
        return ServiceResult({'error': f'Mã hợp đồng "{code}" đã tồn tại. Hãy dùng mã khác.'}, status=400)
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
            version = contract_service.create_new_version(contract_id=contract_id, file_obj=file_obj, raw_content=raw_content, change_summary=change_summary, summarize=summarize_choice(form))
            data_repository.log_contract_action(user, version.contract, f'Added version: v{version.version_number}')
            job = _extract_after_upload(user, int(contract_id))
            return ServiceResult({'success': True, 'version_id': version.id, 'version_number': version.version_number, 'change_summary': version.change_summary,
                                  'extraction_job_id': job and job['id']})
        except Exception as e:
            return ServiceResult({'error': str(e)}, status=400)
    return ServiceResult({'error': 'Method not allowed.'}, status=405)
