"""Database operations for contract operations workflows."""
from contracts.models import Contract

def get_contract_for_contract_detail(contract_id):
    return Contract.objects.get(id=contract_id)

def log_contract_action(user, contract, action, payload=None):
    from contracts.models import AuditLog
    return AuditLog.objects.create(user=user, contract=contract, action=action[:100], payload=payload)

def contract_history_rows(contract_id, limit=100):
    """What was done to a contract, newest first. The request log the audit middleware keeps for every page visit
    and every write is left out: it repeats the named actions and carries raw request bodies."""
    from contracts.models import AuditLog
    rows = AuditLog.objects.filter(contract_id=contract_id).exclude(action__startswith='Visited page').exclude(
        action__startswith='Performed ').exclude(action__startswith='Viewed contract')
    return list(rows.select_related('user').order_by('-created_at', '-pk')[:limit])
