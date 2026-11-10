"""Contract summaries through the standalone ai_summary service.

The source is the contract text stored in the database; when a version has none yet, ai_summary reads the uploaded
PDF/DOCX/TXT itself (with its own OCR for scans), so a summary exists even if the extraction pipeline never runs.
"""
import io
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import requests
from django.conf import settings
from django.db import close_old_connections, connection, transaction
from django.utils import timezone

from ai_extract.repositories import ContractSummaryRepository, extraction_repository
from ai_extract.services.extraction_service import ExtractionError

logger = logging.getLogger('ai_extract')
EXPIRY_WINDOW_DAYS = 90
QUEUED_LEASE = 3600  # seconds a run may wait for a slot before it is considered lost
AUTO_SLOTS = threading.BoundedSemaphore(int(os.environ.get('AI_SUMMARY_AUTO_PARALLEL', '2')))


class SummaryBusy(ExtractionError):
    """A run for this version is already in progress."""


def call_summary(path, payload=None, files=None, form=None):
    """Call ai_summary (JSON body, or multipart files + form fields); non-2xx answers surface its detail."""
    from shared.jwt_middleware import get_system_auth_header
    url = getattr(settings, 'AI_SUMMARY_URL', '').rstrip('/') + path
    timeout = getattr(settings, 'AI_SUMMARY_TIMEOUT', 600)
    try:
        if files is not None:
            response = requests.post(url, files=files, data=form or {}, headers=get_system_auth_header(), timeout=timeout)
        elif payload is not None:
            response = requests.post(url, json=payload, headers=get_system_auth_header(), timeout=timeout)
        else:
            response = requests.get(url, timeout=10)
        data = response.json()
    except (requests.RequestException, ValueError) as e:
        raise RuntimeError(f'ai_summary không phản hồi ({url}): {e}') from e
    if not response.ok and (payload is not None or files is not None):
        detail = data.get('detail', data) if isinstance(data, dict) else data
        if response.status_code in (400, 413, 415, 422):  # the file or text itself is the problem
            raise ExtractionError(f'ai_summary: {detail}', 422)
        raise RuntimeError(f'ai_summary {response.status_code}: {detail}')
    return data


def flag(value):
    """A boolean from JSON (True) or from a multipart form ('true', 'on'); the string 'false' is False."""
    return value.strip().lower() in ('1', 'true', 'on', 'yes') if isinstance(value, str) else bool(value)


def render_options(data):
    """Audience, length and glossary options accepted by ai_summary; anything else falls back to defaults."""
    perspective, length = data.get('perspective', 'general'), data.get('length', 'detailed')
    return dict(perspective=perspective if perspective in ('general', 'employee', 'hr') else 'general',
                length=length if length in ('one_sentence', 'short', 'detailed') else 'detailed',
                explain_terms=flag(data.get('explain_terms', False)))


DEFAULT_OPTIONS = dict(perspective='general', length='detailed', explain_terms=False)


def form_fields(options, force=False, metadata=None):
    """Multipart form values: booleans as 'true'/'false', metadata as JSON."""
    fields = {k: str(v).lower() if isinstance(v, bool) else v for k, v in (options or render_options({})).items()}
    fields['force'] = 'true' if force else 'false'
    if metadata:
        fields['contract_metadata'] = json.dumps(metadata, ensure_ascii=False)
    return fields


def version_file(version):
    source = ContractSummaryRepository.source_file(version)
    if not source:
        raise ExtractionError(f'Phiên bản v{version.version_number} chưa có text hay file để tóm tắt.')
    return source


def select_version(user, contract_id, version_id=None):
    contract = extraction_repository.contract_for(user, contract_id)
    version = extraction_repository.version_for(contract, version_id)
    if version is None:
        raise ExtractionError('Contract has no version yet.')
    return contract, version


class SummarizeService:
    """Send a version's original file to ai_summary and persist the result."""

    def summarize_version(self, version, force=False, options=None, refresh=False) -> dict:
        """refresh: the stored summary is known to be out of date, so this counts as a run even without force."""
        source = version_file(version)
        metadata = {'contract_code': version.contract.contract_code, 'title': version.contract.title,
                    'version': version.version_number}
        logger.info('[summarize] ai_summary request – version_id=%s file=%s (%d bytes)', version.id, source['name'], len(source['data']))
        default_view = (options or DEFAULT_OPTIONS) == DEFAULT_OPTIONS
        # Another view of a summary that is still current only re-renders the cached analysis: no run to track or
        # lock. A missing or out-of-date summary needs a new analysis, which is a run whatever view asked for it.
        current = ContractSummaryRepository.get_by_version(version)
        out_of_date = bool(current and current.source_fingerprint and current.source_fingerprint != source['fingerprint'])
        tracked = force or refresh or current is None or out_of_date
        if tracked and not ContractSummaryRepository.try_start_run(version.id, run_lease(), source['fingerprint']):
            raise SummaryBusy('Phiên bản này đang được tóm tắt, vui lòng đợi kết quả.', 409)
        data, stored = self._run(version, source, force, options, metadata, tracked, default_view)
        saved = stored is not None
        if saved:
            obj = ContractSummaryRepository.create_or_update(
                version=version, summary=stored['summary'], model_id=stored.get('model_id', ''),
                result={**{k: v for k, v in stored.items() if k not in ('summary', 'facts', 'cached', 'elapsed_ms')}, 'origin': source['origin']},
                fingerprint=source['fingerprint'], analysis_version=stored.get('analysis_version', ''))
            logger.info('[summarize] Saved ContractSummary id=%s cached=%s %sms', obj.id, data.get('cached'), data.get('elapsed_ms'))
        if tracked:
            set_status(version.id, 'done')
        return {'version_id': version.id, 'contract_id': version.contract.id, 'saved': saved, 'origin': source['origin'], **data}

    def _run(self, version, source, force, options, metadata, tracked, default_view):
        """The result for this view, and the default view to store (None when nothing needs storing)."""
        files = {'file': (source['name'], source['data'])}
        try:
            data = call_summary('/api/v1/summarize-file', files=files, form=form_fields(options, force, metadata))
            if default_view:
                return data, data
            if tracked:  # the analysis is new: refresh the stored default view too (from ai_summary's cache)
                return data, call_summary('/api/v1/summarize-file', files=files, form=form_fields(DEFAULT_OPTIONS, False, metadata))
            return data, None
        except RuntimeError as error:  # the model or the service is down, not a problem with this file
            if tracked:
                ContractSummaryRepository.set_fallback(version.id, self._preliminary(files))
                set_status(version.id, 'failed', str(error))
            raise
        except Exception as error:
            if tracked:
                set_status(version.id, 'failed', str(error))
            raise

    @staticmethod
    def _preliminary(files):
        try:
            return call_summary('/api/v1/read', files=files).get('preliminary', '')
        except (ExtractionError, RuntimeError):
            return ''


# Status of the automatic summary started after an upload: running / done / failed (+ error).
def run_lease():
    return getattr(settings, 'AI_SUMMARY_TIMEOUT', 600) + 60


def set_status(version_id, state, error=''):
    ContractSummaryRepository.set_run_status(version_id, state, error)


def _row_state(row):
    return (_status_of(row) or {}).get('state') if row and row.get('run_status') else None


def get_status(version_id):
    return _status_of(ContractSummaryRepository.run_status(version_id))


def _status_of(row):
    """The stored run state; one left in progress past its lease died with its process and is reported as failed."""
    if not row:
        return None
    state = row['run_status']
    lease = {'queued': QUEUED_LEASE, 'running': run_lease()}.get(state)
    if lease and row['run_status_at'] and (timezone.now() - row['run_status_at']).total_seconds() > lease:
        return {'state': 'failed', 'error': 'Lần tóm tắt trước bị gián đoạn (dịch vụ đã khởi động lại). Hãy bấm thử lại.'}
    return {'state': state, 'error': row['run_error']}


def schedule_auto_summary(version, requested=None):
    """After an upload commits, summarize the new version in the background; upload never waits or fails on it.

    requested is the uploader's choice; None falls back to AI_SUMMARY_AUTO.
    """
    if not (getattr(settings, 'AI_SUMMARY_AUTO', False) if requested is None else requested):
        return
    version_id = version.id
    set_status(version_id, 'queued')
    # robust: the upload is already committed, so a failure to start the summary must not turn it into an error.
    transaction.on_commit(lambda: threading.Thread(target=_auto_summary, args=(version_id,), daemon=True,
                                                   name=f'auto-summary-{version_id}').start(), robust=True)


def _recycle_connection():
    """Drop a stale connection before/after a background run, but never inside a transaction: Django would close
    the caller's connection outright (autocommit is off there) and every later query would fail."""
    if not connection.in_atomic_block:
        close_old_connections()


def _auto_summary(version_id):
    with AUTO_SLOTS:  # a bulk upload waits as 'queued' instead of flooding the single model
        _auto_summary_now(version_id)


def _auto_summary_now(version_id):
    _recycle_connection()
    try:
        version = ContractSummaryRepository.version_by_id(version_id)
        SummarizeService().summarize_version(version)
    except SummaryBusy:
        logger.info('[summarize] version %s already being summarized', version_id)
    except Exception as error:
        logger.warning('[summarize] automatic summary of version %s failed: %s', version_id, error)
        set_status(version_id, 'failed', str(error))
    finally:
        _recycle_connection()


def model_info():
    """ai_summary's health answer when its model is reachable, else None."""
    try:
        health = call_summary('/health')
    except RuntimeError:
        return None
    return health if health.get('llm_connected') else None


class SettleTracker:
    """Text arrives page by page, so a version is ready only once its text stayed the same for a while."""

    def __init__(self, seconds, clock=time.monotonic):
        self.seconds, self.clock, self.seen = seconds, clock, {}

    def ready(self, fingerprints):
        now = self.clock()
        self.seen = {version_id: (fingerprint, self.seen[version_id][1] if self.seen.get(version_id, (None,))[0] == fingerprint else now)
                     for version_id, fingerprint in fingerprints.items()}
        return [version_id for version_id, (_, since) in self.seen.items() if now - since >= self.seconds]


def _worker_run(version_id):
    _recycle_connection()
    try:
        SummarizeService().summarize_version(ContractSummaryRepository.version_by_id(version_id), refresh=True)
        return True
    except SummaryBusy:
        return False
    except Exception as error:
        logger.warning('[summarize] run for version %s failed: %s', version_id, error)
        return False
    finally:
        _recycle_connection()


def retry_failed_runs(settle=None, parallel=1):
    """Summarize what is waiting, newest first: text with no summary or an out-of-date one, and runs that failed
    while the model was down. Returns the number completed; nothing happens while the model is down."""
    info = model_info()
    if not info:
        return 0
    lost_before = timezone.now() - timedelta(seconds=QUEUED_LEASE)
    version_ids = set(ContractSummaryRepository.retryable_version_ids(lost_before))
    if getattr(settings, 'AI_SUMMARY_AUTO', False):
        needed = ContractSummaryRepository.versions_needing_summary(info.get('analysis_version', ''))
        version_ids.update(settle.ready(needed) if settle else needed)
    ordered = sorted(version_ids, reverse=True)
    if parallel <= 1:
        return sum(_worker_run(version_id) for version_id in ordered)
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        return sum(pool.map(_worker_run, ordered))


def summarize(user, contract_id, data):
    _, version = select_version(user, contract_id, data.get('version_id'))
    return SummarizeService().summarize_version(version, force=bool(data.get('force', False)), options=render_options(data))


def summary(user, contract_id, version_id=None):
    """The stored summary of a version (None when there is none yet) and the state of its automatic run."""
    contract, version = select_version(user, contract_id, version_id)
    obj = ContractSummaryRepository.get_by_version(version)
    record = ContractSummaryRepository.latest_file(version)
    stored = ContractSummaryRepository.stored_result(version.id)
    fingerprint = ContractSummaryRepository.text_fingerprints([version.id]).get(version.id)
    return dict(id=obj.id if obj else None, contract_id=contract.id, version_id=version.id,
                version_number=version.version_number, summary=obj.summary if obj else None,
                result=stored if obj else None, preliminary=stored.get('preliminary', '') if not obj else '',
                has_previous=ContractSummaryRepository.previous_version(version) is not None,
                versions=[dict(id=v.id, number=v.version_number) for v in ContractSummaryRepository.versions_of(contract)],
                stale=bool(obj and fingerprint and obj.source_fingerprint != fingerprint),
                # Whether the worker brings a stale summary up to date by itself, or the person has to re-run it.
                auto_refresh=bool(getattr(settings, 'AI_SUMMARY_AUTO', False)),
                model_id=obj.model_id if obj else '', created_at=obj.created_at.isoformat() if obj else None,
                updated_at=obj.updated_at.isoformat() if obj else None, status=get_status(version.id),
                file_name=ContractSummaryRepository.display_name(record),
                has_text=bool(fingerprint))


def changes_from_previous(user, contract_id, version_id=None, against_id=None):
    """What changed since the previous version, or since against_id; analyses come from ai_summary's cache when they can."""
    _, version = select_version(user, contract_id, version_id)
    previous = select_version(user, contract_id, against_id)[1] if against_id else ContractSummaryRepository.previous_version(version)
    if previous is None or previous.id == version.id:
        return dict(previous_number=None, changes=[], summary='')
    first, second = sorted((previous, version), key=lambda v: v.version_number)  # always described oldest to newest
    old, new = version_file(first), version_file(second)
    data = call_summary('/api/v1/compare-files', files={'old_file': (old['name'], old['data']), 'new_file': (new['name'], new['data'])},
                        form=form_fields(None))
    return dict(previous_number=previous.version_number, changes=data['changes'], summary=data['summary'])


def summary_overview(user):
    """For the contract list: each visible contract's summary state and missing clauses, and what expires soon."""
    contracts = extraction_repository.visible_contract_rows(user)
    latest = ContractSummaryRepository.latest_versions([c['id'] for c in contracts])
    rows = ContractSummaryRepository.summary_rows(latest.values())
    fingerprints = ContractSummaryRepository.text_fingerprints(latest.values())
    today = timezone.localdate()
    auto = getattr(settings, 'AI_SUMMARY_AUTO', False)
    items, expiring = {}, []
    for contract in contracts:
        version_id = latest.get(contract['id'])
        row = rows.get(version_id, {})
        result = row.get('result') or {}
        fingerprint = fingerprints.get(version_id)
        state = _row_state(row)
        if state in (None, 'done') and row.get('summary') and fingerprint and row.get('source_fingerprint') != fingerprint:
            state = 'stale'
        elif state is None and fingerprint and auto and not row.get('summary'):
            state = 'queued'  # the worker picks up text without a summary only while automatic summaries are on
        elif state == 'done' and not row.get('summary'):
            state = None
        gaps = sum(item.get('status') != 'found' for item in (result.get('checklist') or {}).get('items', []))
        end = next((d['date'] for d in result.get('key_dates', []) if d.get('kind') == 'end' and d.get('date')), None)
        days_left = _days_until(end, today)
        end = end if days_left is not None else None
        items[contract['id']] = dict(state=state, has_summary=bool(row.get('summary')), gaps=gaps, end_date=end, days_left=days_left)
        # Recently ended contracts stay listed for one window; ones that ended long ago are no longer news.
        if days_left is not None and -EXPIRY_WINDOW_DAYS <= days_left <= EXPIRY_WINDOW_DAYS:
            expiring.append(dict(contract_id=contract['id'], code=contract['contract_code'], title=contract['title'],
                                 end_date=end, days_left=days_left))
    return dict(contracts=items, expiring=sorted(expiring, key=lambda e: e['days_left']))


def _days_until(value, today):
    """Days from today to an ISO date; None when the stored value is not a valid date."""
    try:
        return (date.fromisoformat(value) - today).days if value else None
    except (TypeError, ValueError):
        return None


def clause_sections(user, contract_id, version_id=None):
    _, version = select_version(user, contract_id, version_id)
    source = version_file(version)
    return call_summary('/api/v1/sections', files={'file': (source['name'], source['data'])})


def export_docx(user, contract_id, version_id=None):
    """(file name, bytes) of the stored summary as a Word document."""
    import docx
    contract, version = select_version(user, contract_id, version_id)
    obj = ContractSummaryRepository.get_by_version(version)
    if not obj:
        raise ExtractionError('Phiên bản này chưa có bản tóm tắt để xuất.', 404)
    document = docx.Document()
    document.add_heading(f'Tóm tắt hợp đồng {contract.contract_code}', level=1)
    document.add_paragraph(f'{contract.title} · phiên bản {version.version_number}')
    for line in obj.summary.splitlines():
        if line.lstrip().startswith('•'):
            document.add_paragraph(line.lstrip(' •'), style='List Bullet')
        elif line.strip():
            document.add_paragraph(line)
    by = f' bởi {obj.model_id}' if obj.model_id else ''
    document.add_paragraph(f'Tạo tự động{by}, cần đối chiếu với hợp đồng gốc trước khi sử dụng.')
    buffer = io.BytesIO()
    document.save(buffer)
    return f'tom-tat-{contract.contract_code}-v{version.version_number}.docx', buffer.getvalue()


def summary_lab_read(user, upload):
    """What the document says about itself, to prefill the upload form; nothing is saved and the model is not called."""
    if upload is None:
        raise ExtractionError("Field 'file' is required.")
    data = call_summary('/api/v1/read', files={'file': (upload.name, upload.read())})
    return dict(suggest=data['suggest'], source=data['source'])


def summary_lab_contract(user, contract_id):
    """What the Summary Lab shows for the latest version: the file ai_summary reads, its text and chunk plan."""
    contract, version = select_version(user, contract_id)
    record = ContractSummaryRepository.latest_file(version)
    read, read_error = None, ''
    try:
        source = version_file(version)
        read = call_summary('/api/v1/read', files={'file': (source['name'], source['data'])})
    except (ExtractionError, ValueError, RuntimeError) as error:
        read_error = str(error)
    saved = ContractSummaryRepository.get_by_version(version)
    return dict(contract=dict(id=contract.id, code=contract.contract_code, title=contract.title),
                version=dict(id=version.id, number=version.version_number),
                versions=[dict(id=v.id, number=v.version_number) for v in ContractSummaryRepository.versions_of(contract)],
                file=dict(name=ContractSummaryRepository.display_name(record), uploaded_at=record.uploaded_at.isoformat()) if record else None,
                has_text=bool(ContractSummaryRepository.stored_text(version)),
                source=dict(read['source'], preview=read['text'][:4000]) if read else None,
                prepare=read['prepare'] if read else None, read_error=read_error,
                auto=get_status(version.id),
                saved_summary=dict(summary=saved.summary, model_id=saved.model_id, updated_at=saved.updated_at.isoformat()) if saved else None)


def summary_lab_text(user, data):
    """Summarize pasted text without persisting anything."""
    text = data.get('text', '')
    if not isinstance(text, str) or not text.strip():
        raise ExtractionError("Field 'text' is required.")
    if data.get('prepare_only'):
        return call_summary('/api/v1/prepare', {'text': text})
    return call_summary('/api/v1/summarize', {'text': text, 'force': bool(data.get('force', False)), **render_options(data)})


def summary_lab_file(user, upload, data):
    """Summarize an uploaded PDF/DOCX/TXT without saving it anywhere."""
    if upload is None:
        raise ExtractionError("Field 'file' is required.")
    return call_summary('/api/v1/summarize-file', files={'file': (upload.name, upload.read())},
                        form=form_fields(render_options(data), flag(data.get('force', False))))


def summary_lab_compare(user, data):
    """Changes between two versions' files, or between two pasted texts."""
    if data.get('contract_id'):
        old, new = (select_version(user, data['contract_id'], data.get(key))[1] for key in ('old_version_id', 'new_version_id'))
        if old.id == new.id:  # checked after the lookup, so another company's contract is still a 404
            raise ExtractionError('Hãy chọn hai phiên bản khác nhau để so sánh.')
        files = {}
        for field, version in (('old_file', old), ('new_file', new)):
            source = version_file(version)
            files[field] = (source['name'], source['data'])
        return call_summary('/api/v1/compare-files', files=files,
                            form=form_fields(render_options(data), bool(data.get('force', False))))
    texts = [data.get('old_text', ''), data.get('new_text', '')]
    if not all(isinstance(t, str) and t.strip() for t in texts):
        raise ExtractionError("Fields 'old_text' and 'new_text' are required.")
    return call_summary('/api/v1/compare', {'old_text': texts[0], 'new_text': texts[1],
                                            'force': bool(data.get('force', False)), **render_options(data)})


def summary_lab_health(user):
    try:
        return call_summary('/health')
    except RuntimeError as error:
        return dict(status='unreachable', llm_connected=False, error=str(error))
