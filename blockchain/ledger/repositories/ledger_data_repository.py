"""Database operations for ledger workflows."""
from contract.contracts.models import ContractSigningCredential, ContractLedgerOperation, AuditLog

def create_audit_log_for_audit(action, canonical, resource, user):
    return AuditLog.objects.create(user=user, action=action, payload=canonical({'resource': resource}))


def order_by_files_for_snapshot(version):
    return version.files.order_by('id')


def get_contract_signing_credential_for_credential_for(key_id, user):
    return ContractSigningCredential.objects.get(pk=key_id, owner=user, company_id=user.company_id, status='ACTIVE')


def get_record_for_prepare(version):
    return type(version).objects.select_for_update().get(pk=version.pk)


def first_contract_ledger_operation_for_prepare(idem):
    return ContractLedgerOperation.objects.filter(idempotency_key=idem).first()


def save_existing_for_prepare(existing):
    return existing.save(update_fields=['manifest', 'expires_at', 'updated_at'])


def create_contract_ledger_operation_for_prepare(canonical, idem, key, kind, manifest, now, op_id, step_id, timedelta, user, version):
    return ContractLedgerOperation.objects.create(id=op_id, company_id=user.company_id, version=version, actor=user, credential=key, kind=kind, step_id=step_id, idempotency_key=idem, manifest=canonical(manifest), expires_at=now + timedelta(minutes=10), next_attempt_at=now, workflow_synced=not bool(step_id))


def get_contract_ledger_operation_for_accept(op_id, user):
    return ContractLedgerOperation.objects.select_for_update(of=('self',)).select_related('version__contract', 'credential').get(pk=op_id, actor=user, company_id=user.company_id)


def save_op_for_accept(op):
    return op.save()


def order_by_contract_ledger_operation_for_claim(Q, now):
    return ContractLedgerOperation.objects.select_for_update(skip_locked=True).filter(state__in=['PENDING', 'SUBMITTED', 'FAILED'], accepted_at__isnull=False, next_attempt_at__lte=now, attempts__lt=12).filter(Q(lease_until__isnull=True) | Q(lease_until__lt=now)).order_by('next_attempt_at')


def get_contract_ledger_operation_for_process(op):
    return ContractLedgerOperation.objects.select_for_update().get(pk=op.pk)


def save_current_for_process(current):
    return current.save()


def update_contract_ledger_operation_for_process(exc, op, timedelta, timezone):
    return ContractLedgerOperation.objects.filter(pk=op.pk, lease_token=op.lease_token).update(state='FAILED', last_error=str(exc)[:1000], lease_until=None, next_attempt_at=timezone.now() + timedelta(seconds=min(3600, 5 * 2 ** op.attempts)))


def update_contract_ledger_operation_for_sync_workflow(op):
    return ContractLedgerOperation.objects.filter(pk=op.pk).update(workflow_synced=True, last_error='')


def pending_workflow_operations():
    return list(ContractLedgerOperation.objects.filter(state='CONFIRMED', workflow_synced=False)[:20])


def workflow_sync_failed(operation, message):
    ContractLedgerOperation.objects.filter(pk=operation.pk).update(last_error='Workflow sync pending: '+message[:500])


def unbooked_operations(limit=20):
    """Confirmed Fabric operations the blockchain service's ledger book has not filed yet, oldest first."""
    from contract.contracts.ledger_models import ContractLedgerOperation
    return list(ContractLedgerOperation.objects.filter(state='CONFIRMED', booked_at__isnull=True)
                .select_related('version', 'credential').order_by('confirmed_at')[:limit])


def mark_booked(op, when):
    from contract.contracts.ledger_models import ContractLedgerOperation
    ContractLedgerOperation.objects.filter(pk=op.pk).update(booked_at=when)


def next_claimable_operation(Q, now):
    return order_by_contract_ledger_operation_for_claim(Q, now).first()


def role_has_permission(role, permission_code):
    return role.permissions.filter(permission_code=permission_code).exists()


def reject_contract_ledger_operation_for_process(exc, op):
    """An operation that cannot be written as it stands (refused by the chaincode, or its key, permission or file
    changed): not tried again by the worker; the user may retry it once the cause is fixed."""
    return ContractLedgerOperation.objects.filter(pk=op.pk, lease_token=op.lease_token).update(
        state='REJECTED', last_error=str(exc)[:1000], lease_until=None)


def unrevoked_credentials(limit=20):
    """Keys revoked in the web whose revocation is not on the ledger yet."""
    return list(ContractSigningCredential.objects.filter(status='REVOKED', revocation_tx_id='').order_by('revoked_at')[:limit])


def mark_revoked_on_ledger(key, tx_id):
    ContractSigningCredential.objects.filter(pk=key.pk).update(revocation_tx_id=tx_id)
