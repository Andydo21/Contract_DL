"""The contract web's side of the blockchain service's ledger book.

The web writes to Fabric itself (ledger_service); what Fabric confirmed is then filed by the blockchain service in its
ledger tables (hash proof, transaction, audit, certificate, signature, verification history). A user's registration
also goes there: the service issues the certificate their signing key is bound to on Fabric.
"""
import json
import logging

import requests
from django.conf import settings
from django.utils import timezone

from contracts.repositories import ledger_data_repository

logger = logging.getLogger(__name__)


class LedgerBookError(RuntimeError):
    pass


def post(path, payload, timeout=20):
    token = getattr(settings, 'LEDGER_BOOK_TOKEN', '')
    if not token:
        raise LedgerBookError('LEDGER_BOOK_TOKEN is not set')
    try:
        response = requests.post(settings.BLOCKCHAIN_SERVICE_URL.rstrip('/') + path, data=json.dumps(payload, default=str),
                                 headers={'Content-Type': 'application/json', 'X-Ledger-Book-Token': token}, timeout=timeout)
    except requests.RequestException as error:
        raise LedgerBookError(f'Blockchain service unreachable: {type(error).__name__}') from error
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code != 200 or body.get('status') != 'success':
        raise LedgerBookError(body.get('error') or f'Blockchain service HTTP {response.status_code}')
    return body


def operation_payload(op):
    manifest = json.loads(op.manifest)
    return dict(operation_id=str(op.pk), kind=op.kind, version_id=op.version_id, contract_id=manifest['contract_id'],
                company_id=op.company_id, actor_id=op.actor_id, step_id=op.step_id, document_hash=manifest['document_hash'],
                merkle_root=manifest.get('merkle_root'), tx_id=op.tx_id, block_number=op.block_number, block_hash=op.block_hash,
                confirmed_at=op.confirmed_at.isoformat() if op.confirmed_at else None,
                signature=op.signature_base64 if op.kind == 'SIGN' else '',
                public_key_pem=op.credential.public_key_pem if op.credential_id else '',
                credential_fingerprint=op.credential.fingerprint if op.credential_id else '')


def book_pending(limit=20):
    """File every confirmed operation not yet in the book; one the service cannot take now is tried again later."""
    filed = 0
    for op in ledger_data_repository.unbooked_operations(limit):
        try:
            post('/book/operations/', operation_payload(op))
        except LedgerBookError as error:
            logger.warning('Ledger book: operation %s not filed yet: %s', op.pk, error)
            break
        ledger_data_repository.mark_booked(op, timezone.now())
        filed += 1
    return filed


def record_verification(user, version, results, uploaded_hash):
    """Best effort: a verification is answered from Fabric whether or not the book takes it."""
    checks = [dict(kind=r['kind'], ledger=r.get('ledger_verified'), file=r.get('file_integrity'), upload=r.get('uploaded_file_matches'))
              for r in results]
    ok = bool(results) and all(r.get('ledger_verified') and r.get('file_integrity') is not False
                               and r.get('uploaded_file_matches') is not False for r in results)
    try:
        post('/book/verifications/', dict(version_id=version.pk, user_id=user.pk, company_id=user.company_id, result=ok,
                                           uploaded_hash=uploaded_hash, checks=checks,
                                           reason='' if ok else 'Fabric, file or upload check did not match'))
    except LedgerBookError as error:
        logger.warning('Ledger book: verification of version %s not filed: %s', version.pk, error)


def record_credential(key):
    try:
        post('/book/credentials/', dict(user_id=key.owner_id, status=key.status, public_key_pem=key.public_key_pem))
    except LedgerBookError as error:
        logger.warning('Ledger book: credential %s not filed: %s', key.pk, error)


def register_user(user, company, role):
    """The user's certificate from the blockchain service; raises when the service cannot issue it."""
    return post('/book/users/', dict(user_id=user.pk, username=user.username, company_id=company.pk, role=role.role_name))
