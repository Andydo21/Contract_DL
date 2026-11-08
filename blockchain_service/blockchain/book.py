"""The blockchain service as the ledger book: it records what the contract web has confirmed on Fabric.

The web writes version-bound operations to Fabric itself (an anchor of a version's files, or an RSA signature by an
approved key; the chaincode validates both). Once Fabric confirms one, the web sends it here and this service files it
in the ledger tables: the version's hash proof, the transaction with its block, an audit row, and for a signature the
signer's certificate and the signature. It also issues a user's certificate on registration (bound to a key on Fabric
by the user's first signature) and keeps the verification history. Every write is idempotent on the Fabric tx id.
"""
import hashlib
import json
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import (BlockchainAudit, BlockchainNetwork, BlockchainNode, BlockchainTransaction, DigitalSignature, HashProof,
                     SignatureCertificate, SmartContract, VerificationHistory)

CHANNEL = 'contracts-channel'
CHAINCODE = 'contract_verify'
ISSUER = 'ContractGuard CA'
NODES = (('orderer.example.com', 'grpcs://orderer.example.com:7050', 'OrdererOrg'),
         ('peer0.org1.example.com', 'grpcs://peer0.org1.example.com:7051', 'Org1MSP'),
         ('fabric-gateway', 'http://fabric-gateway:5000', 'Org1MSP'))


def network():
    """The Fabric network and chaincode the web writes to (one row each, created on first use)."""
    net = BlockchainNetwork.objects.filter(network_name=f'Hyperledger Fabric · {CHANNEL}').first()
    if net is None:
        net = BlockchainNetwork.objects.create(network_name=f'Hyperledger Fabric · {CHANNEL}', chain_type='Hyperledger Fabric 2.5',
                                               rpc_endpoint='http://fabric-gateway:5000', status='ACTIVE')
    for name, endpoint, organization in NODES:
        BlockchainNode.objects.get_or_create(network=net, node_name=name, defaults=dict(endpoint=endpoint, organization=organization))
    contract = SmartContract.objects.filter(network=net, contract_name=CHAINCODE).first()
    if contract is None:
        contract = SmartContract.objects.create(network=net, contract_name=CHAINCODE, version='2.0',
                                                contract_address=f'{CHANNEL}/{CHAINCODE}', deployed_at=timezone.now())
    return net, contract


def when(value):
    return (parse_datetime(value) if isinstance(value, str) else value) or timezone.now()


def certificate_for(user_id, *, public_key=None, fingerprint=None):
    """The user's certificate: the one issued at registration, or one issued now. A key bound on Fabric fills it."""
    certificate = SignatureCertificate.objects.filter(user_id=user_id, revoked=False).order_by('-valid_from').first()
    if certificate is None:
        certificate = issue_certificate(user_id)
    if public_key and certificate.public_key != public_key:
        certificate.public_key = public_key
        certificate.certificate_pem = public_key
        certificate.status = 'ACTIVE'
        certificate.signature_algorithm = 'SHA256withRSA'
        certificate.save(update_fields=['public_key', 'certificate_pem', 'status', 'signature_algorithm'])
    return certificate


def issue_certificate(user_id, valid_days=365):
    """A certificate for a registered user; its key is not known yet (PENDING_KEY) until the user's key is used."""
    now = timezone.now()
    return SignatureCertificate.objects.create(user_id=user_id, serial_number=f'CG-{user_id}-{secrets.token_hex(4).upper()}',
                                               issuer=ISSUER, valid_from=now, valid_to=now + timedelta(days=valid_days),
                                               status='PENDING_KEY')


@transaction.atomic
def register_user(data):
    """Registration: one certificate per user (a repeat registration returns the existing one)."""
    certificate = SignatureCertificate.objects.filter(user_id=data['user_id'], revoked=False).first() or issue_certificate(data['user_id'])
    net, _ = network()
    audit(None, data['user_id'], data.get('company_id'), 'USER_REGISTERED', f'user:{data["user_id"]}',
          dict(username=data.get('username'), role=data.get('role'), certificate=certificate.serial_number))
    return dict(certificate_id=certificate.pk, serial_number=certificate.serial_number, certificate_status=certificate.status,
                valid_to=certificate.valid_to.isoformat(), network=net.network_name)


def audit(tx, user_id, company_id, action, resource, after, status='SUCCESS'):
    return BlockchainAudit.objects.create(transaction=tx, user_id=user_id, company_id=company_id, action=action, resource=resource,
                                          after_state=json.dumps(after, ensure_ascii=False, default=str), status=status)


@transaction.atomic
def record_operation(data):
    """A confirmed Fabric operation (ANCHOR or SIGN), filed once per transaction."""
    existing = BlockchainTransaction.objects.filter(tx_hash=data['tx_id']).first()
    if existing:
        return dict(transaction_id=existing.pk, proof_id=existing.proof_id, recorded=False)
    net, contract = network()
    proof = HashProof.objects.select_for_update().filter(version_id=data['version_id']).first()
    if proof is None:
        proof = HashProof.objects.create(version_id=data['version_id'], document_hash=data['document_hash'],
                                         merkle_root=data.get('merkle_root'), verified=True, verified_at=when(data['confirmed_at']))
    elif proof.document_hash != data['document_hash']:
        proof.previous_hash, proof.document_hash, proof.hash_version = proof.document_hash, data['document_hash'], proof.hash_version + 1
        proof.verified, proof.verified_at = True, when(data['confirmed_at'])
        proof.save()
    tx = BlockchainTransaction.objects.create(proof=proof, network=net, smart_contract=contract, tx_hash=data['tx_id'], fabric_tx_id=data['tx_id'],
                                              block_hash=data['block_hash'], block_number=data['block_number'], status='CONFIRMED',
                                              tx_type=data['kind'], sender=str(data['actor_id']), endorser='Org1MSP', channel_name=CHANNEL,
                                              chaincode_name=CHAINCODE, gas_fee=0)
    resource = f'contract:{data["contract_id"]}/version:{data["version_id"]}'
    audit(tx, data['actor_id'], data['company_id'], 'LEDGER_' + data['kind'], resource,
          dict(operation_id=data['operation_id'], document_hash=data['document_hash'], step_id=data.get('step_id')))
    if data['kind'] == 'SIGN':
        certificate = certificate_for(data['actor_id'], public_key=data['public_key_pem'], fingerprint=data.get('credential_fingerprint'))
        DigitalSignature.objects.create(certificate=certificate, hashproof=proof, signature=data['signature'], algorithm='SHA256withRSA',
                                        verified=True, verified_at=when(data['confirmed_at']), tx_hash=data['tx_id'],
                                        block_number=data['block_number'], block_hash=data['block_hash'])
    return dict(transaction_id=tx.pk, proof_id=proof.pk, recorded=True)


@transaction.atomic
def record_verification(data):
    """A verification the web ran against Fabric, with its result."""
    history = VerificationHistory.objects.create(version_id=data['version_id'], verify_result=bool(data['result']),
                                                 user_id=data.get('user_id'), reason=data.get('reason') or '')
    tx = BlockchainTransaction.objects.filter(proof__version_id=data['version_id']).order_by('-block_number').first()
    audit(tx, data.get('user_id'), data.get('company_id'), 'LEDGER_VERIFIED', f'version:{data["version_id"]}',
          dict(result=bool(data['result']), uploaded_hash=data.get('uploaded_hash'), checks=data.get('checks')),
          status='SUCCESS' if data['result'] else 'MISMATCH')
    return dict(verification_id=history.pk)


@transaction.atomic
def record_credential(data):
    """A signing key approved or revoked in the web: the user's certificate follows it."""
    certificate = certificate_for(data['user_id'], public_key=data.get('public_key_pem'))
    if data['status'] == 'REVOKED':
        certificate.revoked, certificate.revoked_at, certificate.status = True, timezone.now(), 'REVOKED'
        certificate.save(update_fields=['revoked', 'revoked_at', 'status'])
    return dict(certificate_id=certificate.pk, serial_number=certificate.serial_number, certificate_status=certificate.status,
                fingerprint=hashlib.sha256((data.get('public_key_pem') or '').encode()).hexdigest()[:16])
