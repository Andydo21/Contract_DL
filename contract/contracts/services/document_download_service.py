from contract.contracts.repositories import document_download_data_repository as data_repository
from django.core.exceptions import ObjectDoesNotExist
from contract.contracts.services.contract_service import ContractService
from contract.core.services.results import ServiceResult
from contract.core.services.access_service import check_contract_permission as _check_contract_permission
contract_service = ContractService()


def _attachment(data, content_type, filename):
    from django.utils.http import content_disposition_header
    response = ServiceResult(data, content_type=content_type)
    # filename*=UTF-8''… keeps a Vietnamese file name intact in the browser.
    response['Content-Disposition'] = content_disposition_header(True, filename)
    return response


def _rendered_pdf(contract, version, text, filename):
    """A PDF typeset from the contract's text, for a file that is not a PDF or cannot be read."""
    from contract.contracts.services.pdf_rendering_service import generate_pdf_from_text
    if not text:
        details = contract_service.get_contract_details(contract.id, version_id=version.id) or {}
        text = details.get('raw_content') or contract.title or ''
    pdf = generate_pdf_from_text(title=contract.title or filename, contract_code=contract.contract_code, text_content=text)
    return _attachment(pdf, 'application/pdf', filename)


def download_file(file_id, user, content_type):
    """The stored file as uploaded (decrypted); a file that cannot be read is replaced by a PDF of the contract text."""
    import mimetypes
    import os
    from contract.contracts.models import ContractFile
    from contract.core.services.stored_file_service import read_decrypted
    try:
        cf = data_repository.get_contract_file_for_download_file(file_id)
        if not _check_contract_permission(user, cf.version.contract):
            return ServiceResult('Permission Denied: You do not have access to this file.', status=403, content_type='text/html')
    except ContractFile.DoesNotExist:
        raise ObjectDoesNotExist('File not found')
    data = read_decrypted(cf.file_path)
    if data is not None:
        if cf.file_name.lower().endswith('.pdf') and data.startswith(b'%PDF'):
            return _attachment(data, 'application/pdf', cf.file_name)
        return _attachment(data, mimetypes.guess_type(cf.file_name)[0] or 'application/octet-stream', cf.file_name)
    return _rendered_pdf(cf.version.contract, cf.version, '', os.path.splitext(cf.file_name)[0] + '.pdf')


def download_contract_pdf(contract_id, user, query):
    """The version's document as a PDF: the uploaded PDF itself, or one typeset from its text."""
    from contract.contracts.models import Contract, ContractVersion
    from contract.core.services.stored_file_service import read_decrypted
    try:
        c = data_repository.get_contract_for_download_contract_pdf(contract_id)
        if not _check_contract_permission(user, c):
            return ServiceResult('Permission Denied: You do not have access to this contract.', status=403, content_type='text/html')
    except Contract.DoesNotExist:
        raise ObjectDoesNotExist('Contract not found')
    version_id = query.get('version_id')
    version = c.latest_version
    if version_id:
        try:
            version = data_repository.get_versions_for_download_contract_pdf(c, version_id)
        except ContractVersion.DoesNotExist:
            pass
    if not version:
        raise ObjectDoesNotExist('Version not found')
    filename = f"{c.contract_code or 'contract'}_v{version.version_number}.pdf"
    latest_file = data_repository.first_files_for_download_contract_pdf(version)
    data = read_decrypted(latest_file.file_path) if latest_file else None
    if data is None:
        return _rendered_pdf(c, version, '', filename)
    if latest_file.file_name.lower().endswith('.pdf') and data.startswith(b'%PDF'):
        return _attachment(data, 'application/pdf', latest_file.file_name)
    return _rendered_pdf(c, version, data.decode('utf-8', errors='ignore'), filename)
