"""Durable, incremental cross-contract identity work outside the A2 request path."""
import json
import logging
import time
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from ai_extract.models import LayoutExtractionRun
from ai_extract.repositories import document_graph_repository as repository, layout_repository
from ai_extract.services.document_graph_service import resolve_shared_entities


class Command(BaseCommand):
    help = 'Resolve shared entities for completed graph snapshots; retry failures without re-extracting sources.'

    def add_arguments(self, parser):
        parser.add_argument('--watch',action='store_true',help='Keep processing newly completed snapshots.')
        parser.add_argument('--run-id',type=int,help='Queue a completed run through the normal graph synchronization flow.')

    def handle(self,*args,**options):
        repository.entity_schema()
        if options['run_id']:
            call_command('sync_document_graph',run_id=options['run_id'],stdout=self.stdout)
        try:
            while True:
                scope=repository.claim_entity_job()
                if scope is None:
                    if not options['watch']:return
                    time.sleep(5);continue
                run=LayoutExtractionRun.objects.select_related('version__contract').filter(
                    pk=scope['run_id'],status='COMPLETED',version_id=scope['version_id'],
                    version__contract__company_id=scope['company_id']).first()
                try:
                    latest=layout_repository.latest_run(run.version,completed=True) if run else None
                    if (not run or not latest or latest.pk!=run.pk
                            or run.structure.get('source_fingerprint')!=scope['fingerprint']
                            or run.structure.get('graph_index',{}).get('status')!='ready'):
                        result=dict(status='complete',skipped='retired_or_unavailable_source')
                    else:
                        result=resolve_shared_entities(scope)
                except Exception as error:
                    logging.getLogger(__name__).exception('Entity resolution failed for run %s',scope['run_id'])
                    result=dict(status='unavailable',error_type=type(error).__name__)
                repository.finish_entity_job(scope,result)
                self.stdout.write(json.dumps(dict(event='entity_resolution',run=scope['run_id'],**result),ensure_ascii=False))
                self.stdout.flush()
                if result['status']!='complete':
                    if not options['watch']:raise CommandError('Identity job remains pending; no identity was inferred from similarity alone.')
                    time.sleep(30)
        except KeyboardInterrupt:
            return
