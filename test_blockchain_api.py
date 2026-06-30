import os, django, sys
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
import requests, json

# Test blockchain status for a few contracts
for contract_id in [11, 12, 13]:
    r = requests.get(f'http://localhost:8000/api/contracts/{contract_id}/blockchain/status/')
    if r.status_code != 200:
        print(f"Contract {contract_id}: ERROR {r.status_code}")
        continue
    data = r.json()
    print(f"\nContract: {data['contract_code']}")
    for v in data['versions']:
        bc = v['blockchain']
        verified = bc.get('verified', False)
        anchored = bc.get('blockchain_anchored', False)
        msg = bc.get('message', '')
        print(f"  v{v['version_number']}: verified={verified} anchored={anchored} -> {msg}")
