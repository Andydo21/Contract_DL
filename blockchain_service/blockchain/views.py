import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .services import (
    CertificateService, ProofService, BlockchainAnchorService,
    VerificationService, SignatureService
)

def health_check(request):
    return JsonResponse({"status": "healthy", "service": "blockchain-django-service"})

@csrf_exempt
def create_certificate(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        body = json.loads(request.body)
        user_id = body['user_id']
        serial_number = body['serial_number']
        issuer = body['issuer']
        valid_days = body.get('valid_days', 365)
        
        cert = CertificateService.register_certificate(
            user_id=user_id,
            serial_number=serial_number,
            issuer=issuer,
            valid_days=valid_days
        )
            
        return JsonResponse({
            "certificate_id": cert.id,
            "user_id": cert.user_id,
            "serial_number": cert.serial_number,
            "issuer": cert.issuer,
            "valid_from": cert.valid_from.isoformat(),
            "valid_to": cert.valid_to.isoformat(),
            "status": cert.status
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

@csrf_exempt
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
        
        proof = ProofService.generate_proof(
            version_id=version_id,
            content=content,
            contract_code=contract_code,
            version_number=version_number,
            change_summary=change_summary
        )
            
        return JsonResponse({
            "proof_id": proof.id,
            "version_id": proof.version_id,
            "hash_algorithm": proof.hash_algorithm,
            "document_hash": proof.document_hash,
            "generated_at": proof.generated_at.isoformat()
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

@csrf_exempt
def anchor_proof(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        body = json.loads(request.body)
        proof_id = body['proof_id']
        network_id = body['network_id']
        smart_contract_id = body.get('smart_contract_id')
        
        tx = BlockchainAnchorService.anchor_proof(
            proof_id=proof_id,
            network_id=network_id,
            smart_contract_id=smart_contract_id
        )
        
        return JsonResponse({
            "tx_id": tx.id,
            "proof_id": tx.proof_id,
            "network_id": tx.network_id,
            "smart_contract_id": tx.smart_contract_id,
            "tx_hash": tx.tx_hash,
            "block_hash": tx.block_hash,
            "block_number": tx.block_number,
            "gas_fee": float(tx.gas_fee),
            "status": tx.status,
            "created_at": tx.created_at.isoformat()
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

@csrf_exempt
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
        
        result = VerificationService.verify_proof(
            version_id=version_id,
            content=content,
            contract_code=contract_code,
            version_number=version_number,
            change_summary=change_summary
        )
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

@csrf_exempt
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
