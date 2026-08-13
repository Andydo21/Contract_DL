import django, os, sys

sys.path.insert(0, r"d:\Django_project\RiskDL\blockchain_service")
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
django.setup()

from django.db import connection

tables = [
    'blockchain_blockchainnetwork', 
    'blockchain_smartcontract', 
    'blockchain_hashproof', 
    'blockchain_blockchaintransaction', 
    'blockchain_signaturecertificate', 
    'blockchain_digitalsignature'
]

with connection.cursor() as cursor:
    for t in tables:
        try:
            # We fetch max id and set sequence to max(id)
            cursor.execute(f"SELECT MAX(id) FROM {t}")
            max_id = cursor.fetchone()[0]
            if max_id is not None:
                cursor.execute(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), %s)", [max_id])
                print(f"Reset sequence for {t} to {max_id}")
            else:
                print(f"Table {t} is empty, no reset needed")
        except Exception as e:
            print(f"Error resetting sequence for {t}: {e}")
