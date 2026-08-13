import json
from django.http import JsonResponse
from .services import (
    CertificateService, ProofService, BlockchainAnchorService,
    VerificationService, SignatureService
)
from .models import HashProof, BlockchainTransaction, SignatureCertificate, BlockchainAudit

def health_check(request):
    return JsonResponse({"status": "healthy", "service": "blockchain-django-service"})


def get_stats(request):
    """GET: Aggregate stats + recent transactions for the blockchain explorer UI."""
    from .models import BlockchainTransaction, HashProof, SignatureCertificate, DigitalSignature, BlockchainNetwork
    try:
        total_txs = BlockchainTransaction.objects.count()
        total_proofs = HashProof.objects.count()
        total_certs = SignatureCertificate.objects.count()
        total_sigs = DigitalSignature.objects.count()
        verified_proofs = HashProof.objects.filter(verified=True).count()
        latest_block = BlockchainTransaction.objects.filter(
            block_number__isnull=False
        ).order_by('-block_number').values_list('block_number', flat=True).first() or 0

        # Recent 20 transactions
        recent_txs = BlockchainTransaction.objects.order_by('-created_at')[:20]
        txs_data = [{
            "id": tx.id,
            "tx_hash": tx.tx_hash,
            "block_number": tx.block_number,
            "block_hash": tx.block_hash,
            "status": tx.status,
            "tx_type": tx.tx_type,
            "sender": tx.sender,
            "channel_name": tx.channel_name,
            "chaincode_name": tx.chaincode_name,
            "fabric_tx_id": tx.fabric_tx_id,
            "latency": float(tx.latency) if tx.latency else None,
            "created_at": tx.created_at.isoformat(),
        } for tx in recent_txs]

        # Recent hash proofs
        recent_proofs = HashProof.objects.order_by('-generated_at')[:10]
        proofs_data = [{
            "id": p.id,
            "version_id": p.version_id,
            "document_hash": p.document_hash,
            "hash_algorithm": p.hash_algorithm,
            "verified": p.verified,
            "merkle_root": p.merkle_root,
            "generated_at": p.generated_at.isoformat(),
        } for p in recent_proofs]

        return JsonResponse({
            "stats": {
                "total_transactions": total_txs,
                "total_proofs": total_proofs,
                "total_certificates": total_certs,
                "total_signatures": total_sigs,
                "verified_proofs": verified_proofs,
                "latest_block": latest_block,
            },
            "recent_transactions": txs_data,
            "recent_proofs": proofs_data,
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)



def create_certificate(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        body = json.loads(request.body)
        user_id = body['user_id']
        serial_number = body['serial_number']
        issuer = body['issuer']
        valid_days = body.get('valid_days', 365)
        certificate_pem = body.get('certificate_pem')
        public_key = body.get('public_key')
        signature_algorithm = body.get('signature_algorithm', 'SHA256withRSA')
        
        cert = CertificateService.register_certificate(
            user_id=user_id,
            serial_number=serial_number,
            issuer=issuer,
            valid_days=valid_days,
            certificate_pem=certificate_pem,
            public_key=public_key,
            signature_algorithm=signature_algorithm
        )
            
        return JsonResponse({
            "certificate_id": cert.id,
            "user_id": cert.user_id,
            "serial_number": cert.serial_number,
            "issuer": cert.issuer,
            "valid_from": cert.valid_from.isoformat(),
            "valid_to": cert.valid_to.isoformat(),
            "status": cert.status,
            "signature_algorithm": cert.signature_algorithm
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

def generate_proof(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        body = json.loads(request.body)
        version_id = body['version_id']
        content = body.get('content')
        contract_code = body.get('contract_code', 'CODE')
        version_number = body.get('version_number', 1)
        change_summary = body.get('change_summary', '')
        previous_version_id = body.get('previous_version_id')
        
        proof = ProofService.generate_proof(
            version_id=version_id,
            content=content,
            contract_code=contract_code,
            version_number=version_number,
            change_summary=change_summary,
            previous_version_id=previous_version_id
        )
            
        return JsonResponse({
            "proof_id": proof.id,
            "version_id": proof.version_id,
            "hash_algorithm": proof.hash_algorithm,
            "document_hash": proof.document_hash,
            "file_size": proof.file_size,
            "previous_hash": proof.previous_hash,
            "merkle_root": proof.merkle_root,
            "generated_at": proof.generated_at.isoformat()
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

def anchor_proof(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        body = json.loads(request.body)
        proof_id = body['proof_id']
        network_id = body.get('network_id', 1)
        smart_contract_id = body.get('smart_contract_id', 1)
        sender = body.get('sender', 'System')
        
        tx = BlockchainAnchorService.anchor_proof(
            proof_id=proof_id,
            network_id=network_id,
            smart_contract_id=smart_contract_id,
            sender=sender
        )
        
        return JsonResponse({
            "tx_id": tx.id,
            "proof_id": tx.proof_id,
            "network_id": tx.network_id,
            "smart_contract_id": tx.smart_contract_id,
            "tx_hash": tx.tx_hash,
            "block_hash": tx.block_hash,
            "block_number": tx.block_number,
            "gas_fee": float(tx.gas_fee) if tx.gas_fee else 0.0,
            "status": tx.status,
            "tx_type": tx.tx_type,
            "sender": tx.sender,
            "channel_name": tx.channel_name,
            "chaincode_name": tx.chaincode_name,
            "fabric_tx_id": tx.fabric_tx_id,
            "latency": float(tx.latency) if tx.latency else 0.0,
            "created_at": tx.created_at.isoformat()
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

def verify_proof(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        body = json.loads(request.body)
        version_id = body['version_id']
        content = body.get('content')
        contract_code = body.get('contract_code', 'CODE')
        version_number = body.get('version_number', 1)
        change_summary = body.get('change_summary', '')
        previous_version_id = body.get('previous_version_id')
        user_id = body.get('user_id')
        
        result = VerificationService.verify_proof(
            version_id=version_id,
            content=content,
            contract_code=contract_code,
            version_number=version_number,
            change_summary=change_summary,
            previous_version_id=previous_version_id,
            user_id=user_id
        )
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

def sign_step(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        body = json.loads(request.body)
        step_id = body['step_id']
        user_id = body['user_id']
        certificate_id = body['certificate_id']
        signature_hash = body['signature_hash']
        
        result = SignatureService.verify_and_sign(
            step_id=step_id,
            user_id=user_id,
            certificate_id=certificate_id,
            signature_hash=signature_hash
        )
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

def get_history(request, version_id):
    try:
        proofs = HashProof.objects.filter(version_id=version_id)
        history = []
        for p in proofs:
            txs = BlockchainTransaction.objects.filter(proof=p)
            for tx in txs:
                audits = BlockchainAudit.objects.filter(transaction=tx)
                history.append({
                    "version_id": p.version_id,
                    "document_hash": p.document_hash,
                    "previous_hash": p.previous_hash,
                    "tx_hash": tx.tx_hash,
                    "block_number": tx.block_number,
                    "status": tx.status,
                    "timestamp": tx.created_at.isoformat(),
                    "audits": [
                        {
                            "action": a.action,
                            "resource": a.resource,
                            "status": a.status,
                            "created_at": a.created_at.isoformat()
                        } for a in audits
                    ]
                })
        return JsonResponse({"history": history})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def get_transaction(request, tx_hash):
    try:
        tx = BlockchainTransaction.objects.get(tx_hash=tx_hash)
        return JsonResponse({
            "tx_id": tx.id,
            "tx_hash": tx.tx_hash,
            "block_hash": tx.block_hash,
            "block_number": tx.block_number,
            "status": tx.status,
            "tx_type": tx.tx_type,
            "sender": tx.sender,
            "channel_name": tx.channel_name,
            "chaincode_name": tx.chaincode_name,
            "latency": float(tx.latency) if tx.latency else 0.0,
            "created_at": tx.created_at.isoformat()
        })
    except BlockchainTransaction.DoesNotExist:
        return JsonResponse({"error": "Transaction not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def get_proof(request, version_id):
    try:
        proof = HashProof.objects.get(version_id=version_id)
        return JsonResponse({
            "proof_id": proof.id,
            "version_id": proof.version_id,
            "document_hash": proof.document_hash,
            "previous_hash": proof.previous_hash,
            "merkle_root": proof.merkle_root,
            "verified": proof.verified,
            "verified_at": proof.verified_at.isoformat() if proof.verified_at else None,
            "generated_at": proof.generated_at.isoformat()
        })
    except HashProof.DoesNotExist:
        return JsonResponse({"error": "Proof not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def get_certificate(request, user_id):
    try:
        certs = SignatureCertificate.objects.filter(user_id=user_id)
        data = [{
            "certificate_id": c.id,
            "serial_number": c.serial_number,
            "issuer": c.issuer,
            "valid_from": c.valid_from.isoformat(),
            "valid_to": c.valid_to.isoformat(),
            "status": c.status,
            "revoked": c.revoked
        } for c in certs]
        return JsonResponse({"certificates": data})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def register_company(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        body = json.loads(request.body)
        company_id = body['company_id']
        company_name = body['company_name']
        tax_code = body['tax_code']
        status = body.get('status', 'ACTIVE')
        sender = body.get('sender', 'System')
        
        from .services import EnterpriseRegistryService
        tx = EnterpriseRegistryService.register_company(
            company_id=company_id,
            company_name=company_name,
            tax_code=tax_code,
            status=status,
            sender=sender
        )
        
        return JsonResponse({
            "status": "success",
            "tx_hash": tx.tx_hash,
            "block_number": tx.block_number,
            "block_hash": tx.block_hash,
            "created_at": tx.created_at.isoformat()
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

def register_user(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        body = json.loads(request.body)
        user_id = body['user_id']
        username = body['username']
        company_id = body['company_id']
        role = body['role']
        status = body.get('status', 'ACTIVE')
        sender = body.get('sender', 'System')
        
        from .services import EnterpriseRegistryService
        tx = EnterpriseRegistryService.register_user(
            user_id=user_id,
            username=username,
            company_id=company_id,
            role=role,
            status=status,
            sender=sender
        )
        
        return JsonResponse({
            "status": "success",
            "tx_hash": tx.tx_hash,
            "block_number": tx.block_number,
            "block_hash": tx.block_hash,
            "created_at": tx.created_at.isoformat()
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)
