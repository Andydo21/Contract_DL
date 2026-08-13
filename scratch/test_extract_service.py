import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from ai_extract.services import ClauseExtractService
from contracts.models import Contract

def test():
    sys.stdout.reconfigure(encoding='utf-8')
    print("=== Testing ClauseExtractService ===")
    contract = Contract.objects.filter(contract_code='LEASE-VIN-2026').first()
    if not contract:
        print("Contract LEASE-VIN-2026 not found!")
        return

    svc = ClauseExtractService()
    
    # 1. Test helper method to reconstruct text
    version = contract.latest_version
    print(f"Reconstructed raw text length: {len(svc._get_raw_text(version))}")
    print("First 200 chars:")
    print(svc._get_raw_text(version)[:200])
    
    # 2. Test call (expecting 502/ConnectionError if kaggle server is offline, but checking code execution)
    try:
        print("Calling extract_contract...")
        res = svc.extract_contract(contract.id, re_extract=False)
        print("Success! Result:", res)
    except Exception as e:
        print("Caught expected/unexpected exception:", type(e), e)

if __name__ == '__main__':
    test()
