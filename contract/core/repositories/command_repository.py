"""Queries of the management commands (legal-document import, expert knowledge index, evaluation corpus)."""
from django.contrib.auth import get_user_model

from contract.contracts.models import Company, Contract, ContractVersion


def contract_by_code(code):
    return Contract.objects.filter(contract_code=code).first()


def contracts_by_codes(codes):
    return list(Contract.objects.filter(contract_code__in=codes))


def company_by_tax_code(tax_code, defaults):
    return Company.objects.get_or_create(tax_code=tax_code, defaults=defaults)[0]


def active_user(username):
    return get_user_model().objects.filter(username=username, is_active=True).first()


def active_user_with_company(username):
    """Raises User.DoesNotExist."""
    return get_user_model().objects.select_related('company', 'role').get(username=username, is_active=True)


def lock_user(user):
    return get_user_model().objects.select_for_update().get(pk=user.pk)


def company_version(version_id, company_id):
    """Raises ContractVersion.DoesNotExist."""
    return ContractVersion.objects.get(pk=version_id, contract__company_id=company_id)


def version_with_contract(version_id):
    return ContractVersion.objects.select_related('contract').get(pk=version_id)


def save_version_hash(version):
    version.save(update_fields=['file_hash'])
    return version


def latest_run(version):
    from ai.ai_extract.models import LayoutExtractionRun
    return LayoutExtractionRun.objects.filter(version=version).order_by('-id').first()


def latest_stored_file(version):
    return version.files.order_by('-uploaded_at').first() if version else None


def recent_running_run(version, since):
    from ai.ai_extract.models import LayoutExtractionRun
    return LayoutExtractionRun.objects.filter(version=version, status='RUNNING', started_at__gte=since).exists()
