"""Entry point of the AI service container (riskdl_ai).

It runs, and restarts when one stops: the internal API the web container calls for model calls and searches
(/internal/ai/), the job loop (extraction, graph rerun, risk analysis), the knowledge-search worker and the
document-entity worker. All share the web container's code, database and media files.
"""
import os
import signal
import subprocess
import sys
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

PROCESSES = {
    'api': ['manage.py', 'runserver', '0.0.0.0:8000', '--noreload'],
    'jobs': ['manage.py', 'ai_jobs'],
    'knowledge': ['manage.py', 'knowledge_worker'],
    'entities': ['manage.py', 'resolve_document_entities', '--watch'],
}


class Command(BaseCommand):
    help = 'Run the AI service: internal API, job loop and AI workers.'

    def handle(self, *args, **options):
        if getattr(settings, 'AI_SERVICE_ROLE', 'web') != 'ai':
            raise CommandError('Set AI_SERVICE_ROLE=ai for the AI service container.')
        if not getattr(settings, 'AI_SERVICE_TOKEN', ''):
            raise CommandError('Set AI_SERVICE_TOKEN (shared with the web container).')
        running, stopping = {}, []
        signal.signal(signal.SIGTERM, lambda *_: stopping.append(True))
        while not stopping:
            for name, command in PROCESSES.items():
                process = running.get(name)
                if process is None or process.poll() is not None:
                    if process is not None:
                        self.stdout.write(f'[ai-service] {name} exited with {process.returncode}; restarting')
                        time.sleep(2)
                    running[name] = subprocess.Popen([sys.executable, *command], cwd=str(settings.BASE_DIR), env=os.environ.copy())
                    self.stdout.write(f'[ai-service] started {name} (pid {running[name].pid})')
            time.sleep(2)
        for process in running.values():
            process.terminate()
