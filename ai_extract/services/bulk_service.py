"""Bulk work on many documents from the A3 dashboard: rerun the graph of documents already extracted, or extract
documents just uploaded, one after another in a background process.

A rerun goes in order and each document links only to the documents already done in the job and to those outside it;
the later ones link back when their turn comes (see cross_document_service.link_documents), so every pair of documents
is linked once, on both sides' new trees. One job runs at a time: the GPU runtime serves one document anyway.
The job's state is a JSON file the background process rewrites as it goes; the dashboard polls it."""
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

from django.conf import settings

MODES = ('rerun', 'extract', 'risk')
TERMINAL = {'complete', 'partial', 'failed'}


def job_dir():
    path = Path(settings.MEDIA_ROOT) / 'bulk_jobs'
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_path(job_id):
    if not isinstance(job_id, str) or len(job_id) != 32 or any(c not in '0123456789abcdef' for c in job_id):
        raise ValueError('Invalid bulk job id')
    return job_dir() / f'{job_id}.json'


def read_job(job_id):
    path = job_path(job_id)
    if not path.is_file():
        raise ValueError('Bulk job not found')
    return json.loads(path.read_text(encoding='utf-8'))


def write_job(job):
    job['updated_at'] = time.time()
    path = job_path(job['id'])
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(job, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)


def alive(pid):
    try:
        os.kill(pid, 0)
    except (OSError, TypeError):
        return False
    return True


def jobs():
    """Every job file, oldest first."""
    rows = [json.loads(path.read_text(encoding='utf-8')) for path in job_dir().glob('*.json')]
    return sorted(rows, key=lambda job: job.get('created_at', 0))


def runs_jobs():
    """Whether this process starts jobs: the AI service does when there is one; otherwise the web process itself."""
    from .ai_service_client import delegated
    return not delegated()


def active_job():
    """The job running now, if any. One whose process died is closed as failed; when none runs, the oldest job waiting
    in the queue is started, by the process that runs jobs (the AI service, when there is one). A job's process is only
    checked on the host that started it: another container cannot see its pid."""
    waiting = None
    for job in jobs():
        if job['status'] in TERMINAL:
            continue
        if job['status'] == 'waiting':
            waiting = waiting or job
            continue
        if job.get('host', socket.gethostname()) != socket.gethostname():
            return job
        if job.get('pid') and not alive(job['pid']):
            job['status'], job['error'] = 'failed', 'The background process stopped before finishing'
            write_job(job)
            continue
        return job
    if waiting is not None and runs_jobs():
        return launch(waiting)
    return None


def waiting_contract(contract_id):
    """Whether a job that has not finished still has this contract to process."""
    return any(item['contract_id'] == contract_id and item['status'] in {'waiting', 'running'}
               for job in jobs() if job['status'] not in TERMINAL for item in job['items'])


def launch(job):
    job['status'] = 'queued'
    write_job(job)
    log = open(job_dir() / f'{job["id"]}.log', 'ab')
    process = subprocess.Popen([sys.executable, 'manage.py', 'bulk_documents', '--job', job['id']],
                               cwd=str(settings.BASE_DIR), stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    job['pid'], job['host'] = process.pid, socket.gethostname()
    write_job(job)
    return job


def latest_job(user):
    for path in sorted(job_dir().glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        job = json.loads(path.read_text(encoding='utf-8'))
        if job.get('user_id') == user.pk or user.is_superuser:
            return job
    return None


def start(user, contract_ids, mode, options=None):
    """Queue documents for one background job and start it. options: extraction options (force_ocr, defer_colpali)."""
    from django.core.exceptions import PermissionDenied
    from NewIdea.services.case_rules import can_review
    from ai_extract.repositories import layout_repository
    if mode not in MODES:
        raise ValueError('mode must be rerun, extract or risk')
    # Extraction rewrites documents; a risk analysis only reads one the user may see.
    if mode != 'risk' and not can_review(user):
        raise PermissionDenied('Only a document manager may run bulk extraction')
    if mode not in MODES:
        raise ValueError('mode must be rerun, extract or risk')
    if not isinstance(contract_ids, list) or not contract_ids or len(contract_ids) > 200 \
            or any(type(i) is not int or i <= 0 for i in contract_ids):
        raise ValueError('contract_ids must be a list of 1 to 200 positive integers')
    items = []
    for contract_id in dict.fromkeys(contract_ids):
        contract = layout_repository.contract_for(user, contract_id)
        if not contract.latest_version:
            raise ValueError(f'Contract {contract_id} has no version')
        items.append(dict(contract_id=contract.pk, title=contract.title, status='waiting', run_id=None, error=None))
    job = dict(id=uuid.uuid4().hex, mode=mode, user_id=user.pk, status='waiting', items=items, done=0,
               created_at=time.time(), error=None, pid=None, options=dict(options or {}))
    write_job(job)
    # One job at a time: the GPU runtime serves one document anyway. A new job waits for the one running.
    running = active_job()
    return read_job(job['id']) if running is None or running['id'] != job['id'] else running


def run_queue(poll_seconds=3, once=False):
    """The AI service's job loop: start the oldest waiting job whenever none runs (see active_job)."""
    while True:
        active_job()
        if once:
            return
        time.sleep(poll_seconds)


def extract_after_upload(user, contract_id):
    """Start extracting a document just uploaded; an account that may not run extraction leaves it for a manager."""
    from django.core.exceptions import PermissionDenied
    if not getattr(settings, 'AI_EXTRACT_ON_UPLOAD', True):
        return None
    try:
        return start(user, [contract_id], 'extract')
    except (PermissionDenied, ValueError):
        return None


def run_job(job_id):
    """Background side: process each document in order and record its outcome."""
    from ai_extract.repositories import layout_repository
    from .inference_runtime_service import PipelineProgress
    from .layout_service import LayoutExtractionService, enrich_entity_graph, link_other_documents, reindex_versions
    job = read_job(job_id)
    job.update(status='running', pid=os.getpid())
    write_job(job)
    contracts = layout_repository.contracts_by_ids(i['contract_id'] for i in job['items'])
    finished, failed = [], set()
    for index, item in enumerate(job['items']):
        item.update(status='running', started_at=time.time())
        write_job(job)
        contract = contracts.get(item['contract_id'])
        try:
            if contract is None or contract.latest_version is None:
                raise ValueError('Contract or version no longer exists')
            run = layout_repository.latest_run(contract.latest_version, completed=True)
            if job['mode'] == 'risk':
                if run is None:
                    raise ValueError('Hợp đồng chưa trích xuất xong; chưa thể phân tích rủi ro.')
                from contracts.services import ContractService

                def progress(stage, done, total, item=item):
                    item['progress'] = dict(stage=stage, done=done, total=total)
                    write_job(job)
                ContractService().analyze_contract(contract.pk, user=layout_repository.user_by_id(job['user_id']), progress=progress)
            elif job['mode'] == 'rerun' and run is not None:
                # Documents later in this job that already have a graph link back to this one when they run.
                waiting = {i['contract_id'] for i in job['items'][index+1:]} - {contract.pk}
                enrich_entity_graph(layout_repository.run_with_contract(run.pk),
                                    deferred_contract_ids=waiting)
                list(reindex_versions(contract.latest_version.pk, dense_only=True))
                finished.append((run.pk, waiting))
            else:
                run = LayoutExtractionService().extract_version(contract.latest_version, **job.get('options', {}))
                if run.status != 'COMPLETED':
                    raise RuntimeError(run.error_message or f'Extraction ended {run.status}')
            item.update(status='complete', run_id=run.pk)
        except Exception as error:
            failed.add(item['contract_id'])
            item.update(status='failed', error=f'{type(error).__name__}: {str(error)[:300]}')
        item['finished_at'] = time.time()
        job['done'] = index + 1
        write_job(job)
    # A document that deferred its links to one that then failed links to it now, on that document's old tree.
    for run_id, waiting in finished:
        if waiting & failed:
            run = layout_repository.run_with_contract(run_id)
            link_other_documents(run, PipelineProgress(run.pk))
    job['status'] = 'failed' if len(failed) == len(job['items']) else 'partial' if failed else 'complete'
    write_job(job)
    active_job()  # the next job waiting in the queue
    return job
