from django.core.management.base import BaseCommand,CommandError
from ai_extract.models import LayoutExtractionRun
from ai_extract.services.layout_service import enrich_entity_graph


class Command(BaseCommand):
    help=('Run GLiNER and save entity mentions to the existing Neo4j source graph; preserve OCR and vectors. '
          'With several --run-id values the runs go in order as one bulk rerun: each links only to the documents '
          'already done in it and to those outside it, and the later ones link back when their turn comes, so every '
          'pair of documents is linked once, on both sides\' new trees.')

    def add_arguments(self,parser):
        parser.add_argument('--run-id',type=int,nargs='+',required=True)

    def handle(self,**options):
        ids=list(dict.fromkeys(options['run_id']))
        try:
            runs=[LayoutExtractionRun.objects.select_related('version__contract').get(pk=pk) for pk in ids]
        except LayoutExtractionRun.DoesNotExist as error:
            raise CommandError(str(error)) from error
        done=[]
        for index,run in enumerate(runs):
            waiting={later.version.contract_id for later in runs[index+1:]}-{run.version.contract_id}
            try:
                enrich_entity_graph(run,deferred_contract_ids=waiting)
            except (ValueError,RuntimeError) as error:
                # The runs not reached keep their old trees and will not link back: the finished ones link to them now.
                self.relink(done)
                raise CommandError(f'Run {run.id}: {error}') from error
            done.append(run)
            self.stdout.write(self.style.SUCCESS(f'Run {run.id}: GLiNER={run.structure["knowledge_graph"]["status"]}, '
                                                f'entities={len(run.structure["knowledge_graph"]["entities"])}, Neo4j=ready'
                                                +(f', linking deferred to {len(waiting)} later run(s)' if waiting else '')))

    def relink(self,runs):
        from ai_extract.services.inference_runtime_service import PipelineProgress
        from ai_extract.services.layout_service import link_other_documents
        for run in runs:
            link_other_documents(run,PipelineProgress(run.id))
            self.stdout.write(f'Run {run.id}: relinked to the whole library after the bulk rerun stopped')
