"""The AI service's job loop: start queued extraction / rerun / risk jobs one at a time (see bulk_service)."""
from django.core.management.base import BaseCommand

from ai_extract.services import bulk_service


class Command(BaseCommand):
    help = 'Run queued AI jobs (extraction, graph rerun, risk analysis) one at a time.'

    def add_arguments(self, parser):
        parser.add_argument('--poll', type=float, default=3.0)
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        bulk_service.run_queue(poll_seconds=options['poll'], once=options['once'])
