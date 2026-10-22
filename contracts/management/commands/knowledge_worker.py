"""Durable Qwen search jobs; PostgreSQL skip-locked claims support workers."""
import time
from django.core.management.base import BaseCommand
from NewIdea.services import search_job_service
from NewIdea.services.contract_search_service import search_contract


def process_one():
    return search_job_service.process_next_job(search_contract)


class Command(BaseCommand):
    help = 'Process queued contract knowledge searches.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        # A crashed worker must not leave jobs polling forever. Avoid automatic
        # retries that could repeat expensive inference; the user can resubmit.
        search_job_service.recover_stale_jobs()
        while True:
            worked = process_one()
            if options['once']:
                return
            if not worked:
                time.sleep(0.5)
