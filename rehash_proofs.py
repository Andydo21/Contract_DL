import os, sys, django
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from contracts.blockchain_service import BlockchainService
from contracts.models import ContractVersion

bc = BlockchainService()
versions = ContractVersion.objects.all().order_by('id')
for v in versions:
    try:
        result = bc.generate_hash_proof(v.id)
        print(f"OK version_id={v.id} {v.contract.contract_code} v{v.version_number} -> hash={result.get('document_hash','')[:16]}...")
    except Exception as e:
        print(f"ERR version_id={v.id}: {e}")

print("Done re-hashing all versions.")
