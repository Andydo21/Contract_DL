from django.core.management.base import BaseCommand, CommandError
from ai_extract.services import bulk_service


class Command(BaseCommand):
    help = 'Process one bulk job of the AI Extract dashboard: rerun or extract its documents in order (started by the dashboard).'

    def add_arguments(self, parser):
        parser.add_argument('--job', required=True)

    def handle(self, **options):
        try:
            job = bulk_service.run_job(options['job'])
        except ValueError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(f'Bulk job {job["id"]}: {job["status"]}, '
                          f'{sum(i["status"] == "complete" for i in job["items"])}/{len(job["items"])} complete')
