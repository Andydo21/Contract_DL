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
        try:
            from .repositories import BookRepository
            if not BookRepository.table_exists("blockchain_blockchainnetwork"):
                return
            
            # The network the ledger book files into (channel, chaincode, orderer, peer, gateway).
            from .book import network
            network()
        except Exception as e:
            print("Database seeding deferred:", e)
