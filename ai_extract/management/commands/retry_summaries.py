"""Summarize contract text waiting in the database, and finish runs that failed while the model was down."""
import logging
import os
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from ai_extract.services import summary_service

logger = logging.getLogger('ai_extract')


class Command(BaseCommand):
    help = 'Summarize waiting text and retry runs that failed while the Kaggle model was offline. --watch keeps checking.'

    def add_arguments(self, parser):
        parser.add_argument('--watch', action='store_true', help='Keep running and check every --interval seconds.')
        parser.add_argument('--interval', type=int, default=30)
        parser.add_argument('--settle', type=int, default=int(os.environ.get('AI_SUMMARY_SETTLE_SECONDS', '60')),
                            help='Seconds a text must stay unchanged before it is summarized; it arrives page by page.')
        parser.add_argument('--parallel', type=int, default=int(os.environ.get('AI_SUMMARY_AUTO_PARALLEL', '2')))

    def handle(self, *args, **options):
        settle = summary_service.SettleTracker(options['settle']) if options['watch'] else None
        while True:
            close_old_connections()
            done = summary_service.retry_failed_runs(settle=settle, parallel=options['parallel'])
            if done:
                self.stdout.write(f'Completed {done} summaries.')
            if not options['watch']:
                return
            time.sleep(options['interval'])
