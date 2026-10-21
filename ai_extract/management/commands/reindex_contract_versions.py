from django.core.management.base import BaseCommand
from ai_extract.services import layout_service


class Command(BaseCommand):
    help='Reindex the latest completed extraction per version; preserve source files.'

    def add_arguments(self,parser):
        parser.add_argument('--version-id',type=int)
        parser.add_argument('--dense-only',action='store_true',help='Retry only text vectors; preserve OCR, graph and visual index.')

    def handle(self,**options):
        for run in layout_service.reindex_versions(options['version_id'],dense_only=options['dense_only']):
            self.stdout.write(f'Version {run.version_id}: dense={run.dense_index_status} ({run.dense_points_count}), visual={run.colpali_index_status} ({run.colpali_points_count})')
