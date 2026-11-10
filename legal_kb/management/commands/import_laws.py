"""Build or refresh a legal corpus from the vbpl dataset; unchanged documents are not parsed again."""
import json

from django.core.management.base import BaseCommand, CommandError

from legal_kb.services import import_service as importer


class Command(BaseCommand):
    help = 'Import the documents listed in legal_kb/sources/<domain>.json.'

    def add_arguments(self, parser):
        parser.add_argument('--domain', default='labour', choices=importer.domains())
        parser.add_argument('--data-dir', help='Where the dataset files are kept (default: LEGAL_KB_DATA_DIR).')
        parser.add_argument('--force', action='store_true', help='Parse every document again.')

    def handle(self, *args, **options):
        try:
            report = importer.run(options['domain'], options['data_dir'], options['force'], log=self.stdout.write)
        except importer.CorpusError as error:
            raise CommandError(str(error))
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
