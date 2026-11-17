"""Database operations for contract operations workflows."""
from contract.contracts.models import Contract

def get_contract_for_contract_detail(contract_id):
    return Contract.objects.get(id=contract_id)

def log_contract_action(user, contract, action, payload=None):
    from contract.contracts.models import AuditLog
    return AuditLog.objects.create(user=user, contract=contract, action=action[:100], payload=payload)

def contract_history_rows(contract_id, limit=100):
    """What was done to a contract, newest first. The request log the audit middleware keeps for every page visit
    and every write is left out: it repeats the named actions and carries raw request bodies."""
    from contract.contracts.models import AuditLog
    rows = AuditLog.objects.filter(contract_id=contract_id).exclude(action__startswith='Visited page').exclude(
        action__startswith='Performed ').exclude(action__startswith='Viewed contract')
    return list(rows.select_related('user').order_by('-created_at', '-pk')[:limit])


# ------------------------------------------------------------------ delete contract
def ledger_in_flight_for_delete(contract):
    """Ledger work not finished yet: a signed operation the worker still has to submit or confirm on Fabric, or a
    confirmed one not yet filed in the blockchain-service ledger book."""
    from contract.contracts.ledger_models import ContractLedgerOperation
    ops = ContractLedgerOperation.objects.filter(version__contract=contract)
    return (ops.filter(accepted_at__isnull=False, state__in=['PENDING', 'SUBMITTED']).exists()
            or ops.filter(state='CONFIRMED', booked_at__isnull=True).exists())


def ledger_evidence_for_delete(contract):
    """What stays on Fabric and in the ledger book after the local copy is deleted."""
    from contract.contracts.ledger_models import ContractLedgerOperation
    return [dict(operation_id=str(op['id']), kind=op['kind'], state=op['state'], version_id=op['version_id'],
                 tx_id=op['tx_id'], block_number=op['block_number'])
            for op in ContractLedgerOperation.objects.filter(version__contract=contract).order_by('created_at').values(
                'id', 'kind', 'state', 'version_id', 'tx_id', 'block_number')]


def dependents_for_delete(contract):
    """Counts of what goes with the contract, for the confirmation and the audit record."""
    from ai.ai_extract.models import LegalDocument
    from contract.contracts.ledger_models import ContractLedgerOperation
    return dict(ledger_operations=ContractLedgerOperation.objects.filter(version__contract=contract).count(),
                legal_document=LegalDocument.objects.filter(contract=contract).exists())


def version_ids_for_delete(contract):
    return list(contract.versions.order_by('id').values_list('id', flat=True))


def stored_paths_for_delete(contract):
    """Uploaded files and page images of every version, as storage-relative names."""
    from ai.ai_extract.models import LayoutExtractionPage
    from contract.contracts.models import ContractFile
    files = list(ContractFile.objects.filter(version__contract=contract).values_list('file_path', flat=True))
    pages = list(LayoutExtractionPage.objects.filter(run__version__contract=contract)
                 .exclude(image_path='').values_list('image_path', flat=True))
    return files, pages


def delete_contract_records(contract, user, payload):
    """Delete the contract and everything that cascades from it; its audit trail is kept, detached and labelled."""
    from django.db import transaction
    from django.db.models import Value
    from django.db.models.functions import Coalesce, Concat
    from contract.contracts.ledger_models import ContractLedgerOperation
    from contract.contracts.models import AuditLog, KnowledgeSearchLog
    with transaction.atomic():
        # the search history goes with the contract (it quotes the contract's text)
        KnowledgeSearchLog.objects.filter(version__contract=contract).delete()
        # the local copy of ledger operations; the transactions themselves stay on Fabric and in the ledger book
        ContractLedgerOperation.objects.filter(version__contract=contract).delete()
        AuditLog.objects.filter(contract=contract).update(
            contract=None, payload=Concat(Value(f'[contract {contract.contract_code}] '), Coalesce('payload', Value(''))))
        contract.delete()
        AuditLog.objects.create(user=user, contract=None, action='DELETE_CONTRACT', payload=payload)
