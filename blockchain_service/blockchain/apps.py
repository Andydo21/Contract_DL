from django.apps import AppConfig
import threading
import sys

class BlockchainConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'blockchain'

    def ready(self):
        # Run seeding in a background thread so it doesn't block startup
        if 'manage.py' in sys.argv and ('runserver' in sys.argv or 'wsgi' in sys.argv or 'asgi' in sys.argv or 'uvicorn' in sys.argv):
            threading.Thread(target=self.seed_database, daemon=True).start()

    def seed_database(self):
        import time
        # Give some time for migrations to complete
        time.sleep(5)
        from django.utils import timezone
        from .models import BlockchainNetwork, SmartContract, BlockchainNode
        from django.db import connection
        try:
            with connection.cursor() as cursor:
                tables = connection.introspection.table_names()
                if "blockchain_blockchainnetwork" not in tables:
                    return
            
            if not BlockchainNetwork.objects.exists():
                net = BlockchainNetwork.objects.create(
                    network_name="Hyperledger Fabric Local",
                    chain_type="Hyperledger",
                    rpc_endpoint="http://fabric-peer:7051",
                    status="ACTIVE"
                )
                SmartContract.objects.create(
                    network=net,
                    contract_address="cc_contract_verify_v1",
                    contract_name="ContractVerifyChaincode",
                    version="1.0.0",
                    deployed_at=timezone.now()
                )
                BlockchainNode.objects.create(
                    network=net,
                    node_name="Peer0Org1",
                    endpoint="fabric-peer:7051",
                    organization="Org1MSP",
                    status="ACTIVE"
                )
                print("Seeded default Hyperledger network inside blockchain microservice.")
        except Exception as e:
            print("Database seeding deferred:", e)
