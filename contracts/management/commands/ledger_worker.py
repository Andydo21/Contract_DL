import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from contracts.services import ledger_service as ledger
from contracts.repositories import ledger_data_repository


class Command(BaseCommand):
    help = 'Process and reconcile the durable Fabric outbox; --once runs one batch.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            op = ledger.claim()
            if op:
                ledger.process(op)
            # What Fabric confirmed goes into the blockchain service's ledger book (retried until it is filed).
            from contracts.services.ledger_book_service import book_pending
            book_pending()
            for pending in ledger_data_repository.pending_workflow_operations():
                try:
                    ledger.sync_workflow(pending)
                except Exception as exc:
                    ledger_data_repository.workflow_sync_failed(pending, str(exc))
            if options['once']:
                break
            if not op:
                time.sleep(3)
