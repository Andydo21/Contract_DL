"""Contract authorization policy shared by the web endpoints."""

MANAGER_ROLES = {'MANAGER', 'ADMIN'}


def is_manager(user):
    """A superuser, or a user whose role is MANAGER or ADMIN."""
    return bool(user.is_superuser or (user.role and user.role.role_name.upper() in MANAGER_ROLES))


def is_admin(user):
    """A superuser, or a user whose role is ADMIN."""
    return bool(user.is_superuser or (getattr(user, 'role', None) and user.role.role_name.upper() == 'ADMIN'))


def check_contract_permission(user, contract):
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or bool(user.company_id and user.company_id == contract.company_id)


def contract_access_error(user, contract_id):
    """Check scope before reading versions or contacting another service."""
    from contract.contracts.repositories.contract_repository import ContractRepository
    from contract.core.services.results import ServiceResult
    contract = ContractRepository.get_contract(contract_id)  # a scope check needs no versions or analyses
    if contract is None:
        return ServiceResult({'error': 'Contract not found.'}, status=404)
    if not check_contract_permission(user, contract):
        return ServiceResult({'error': 'Permission denied.'}, status=403)
    return None
