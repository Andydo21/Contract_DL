"""HTTP views of the contract summary service: plain text or an uploaded PDF/DOCX/TXT file in, a structured,
source-verified summary out. The work is in services/summary_service.py; these views only read the request,
check it and map errors to status codes (400 bad input, 422 unreadable file or bad option, 502 model failure)."""
import json
import logging

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from pydantic import ValidationError

from ai.ai_summary.schemas import CompareRequest, RenderOptions, SummarizeRequest
from ai.ai_summary.services import insights_service as insights
from ai.ai_summary.services import llm_service as llm
from ai.ai_summary.services import reader_service as reader
from ai.ai_summary.services import request_guard
from ai.ai_summary.services import summary_service as services
from contract.core.services.access_service import is_admin
from contract.core.views.access import api_login_required

logger = logging.getLogger('ai_summary')


class RequestError(Exception):
    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


def summary_api(view):
    """Map the service's errors to JSON responses, as the FastAPI version did."""
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except (RequestError, request_guard.GuardError) as error:
            return JsonResponse({'detail': str(error)}, status=error.status)
        except ValidationError as error:
            return JsonResponse({'detail': error.errors(include_url=False)}, status=422, json_dumps_params={'default': str})
        except reader.ReadError as error:
            return JsonResponse({'detail': str(error)}, status=422)
        except ValueError as error:
            return JsonResponse({'detail': str(error)}, status=400)
        except llm.LLMError as error:
            logger.warning('summary model failed: %s', error)
            return JsonResponse({'detail': str(error)}, status=502)
    wrapped.__name__ = view.__name__
    wrapped.__doc__ = view.__doc__
    return wrapped


def json_body(request):
    try:
        return json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError):
        raise RequestError('Body must be JSON.', 400)


def read_upload(request, field):
    upload = request.FILES.get(field)
    if upload is None:
        raise RequestError(f'Missing file field "{field}".', 422)
    request_guard.check(request.user, uploads=[upload], model_call=False)  # before reading it into memory
    return services.read_document(upload.read(), upload.name or '')


def guard(request, force=False, texts=(), fields=()):
    """Size, force and per-minute limits for a route that may call the model; checked before any work."""
    request_guard.check(request.user, force=force, texts=texts, uploads=[request.FILES.get(f) for f in fields])


def form_options(request):
    return RenderOptions(perspective=request.POST.get('perspective', 'general'),
                         length=request.POST.get('length', 'detailed'),
                         explain_terms=request.POST.get('explain_terms', 'false').lower() in ('1', 'true', 'yes', 'on'))


def form_flag(request, name):
    return request.POST.get(name, 'false').lower() in ('1', 'true', 'yes', 'on')


def source_info(document):
    """What was read from the file, without the text itself."""
    return {k: v for k, v in document.items() if k != 'text'}


@require_POST
@api_login_required
@summary_api
def summarize_contract(request):
    """Summary of a plain text (JSON: text, contract_metadata, perspective, length, explain_terms, force, model)."""
    payload = SummarizeRequest(**json_body(request))
    guard(request, payload.force, [payload.text])
    return JsonResponse(services.summarize(payload.text, payload.contract_metadata, payload.force, payload.model,
                                           payload.perspective, payload.length, payload.explain_terms))


@require_POST
@api_login_required
@summary_api
def compare_versions(request):
    """Summaries of two versions (or a contract and its amended text) and the field-level changes."""
    payload = CompareRequest(**json_body(request))
    guard(request, payload.force, [payload.old_text, payload.new_text])
    return JsonResponse(services.compare(payload.old_text, payload.new_text, payload.force, payload.model,
                                         payload.perspective, payload.length, payload.explain_terms))


@require_POST
@api_login_required
@summary_api
def prepare_contract(request):
    """Sections, facts and chunk plan for a text; no model call."""
    payload = SummarizeRequest(**json_body(request))
    request_guard.check(request.user, texts=[payload.text], model_call=False)
    return JsonResponse(services.prepare(payload.text))


@require_POST
@api_login_required
@summary_api
def read_file(request):
    """Text read from a PDF/DOCX/TXT file plus the chunk plan; no model call."""
    document = read_upload(request, 'file')
    return JsonResponse({'source': source_info(document), 'text': document['text'],
                         'prepare': services.prepare(document['text']),
                         'preliminary': insights.preliminary(document['text']), 'suggest': insights.suggest(document['text'])})


@require_POST
@api_login_required
@summary_api
def file_sections(request):
    """Clause text by the label summaries cite ("Điều 3"), so a citation can open the source; no model call."""
    return JsonResponse({'sections': services.sections_by_label(read_upload(request, 'file')['text'])})


@require_POST
@api_login_required
@summary_api
def summarize_file(request):
    """Read an uploaded file and summarize it."""
    options = form_options(request)
    guard(request, form_flag(request, 'force'), fields=['file'])
    document = read_upload(request, 'file')
    metadata = json.loads(request.POST.get('contract_metadata') or '{}')
    result = services.summarize(document['text'], metadata, form_flag(request, 'force'), request.POST.get('model') or None,
                                options.perspective, options.length, options.explain_terms)
    return JsonResponse({**result, 'source': source_info(document)})


@require_POST
@api_login_required
@summary_api
def compare_files(request):
    options = form_options(request)
    guard(request, form_flag(request, 'force'), fields=['old_file', 'new_file'])
    old, new = read_upload(request, 'old_file'), read_upload(request, 'new_file')
    result = services.compare(old['text'], new['text'], form_flag(request, 'force'), request.POST.get('model') or None,
                              options.perspective, options.length, options.explain_terms)
    return JsonResponse({**result, 'old_source': source_info(old), 'new_source': source_info(new)})


@require_GET
def health_check(request):
    connected = llm.is_connected()
    # Open for monitoring, so the address of the model server (an internal URL) is shown to administrators only.
    show_url = request.user.is_authenticated and is_admin(request.user)
    return JsonResponse({
        'status': 'healthy' if connected else 'degraded',
        **({'llm_url': llm.base_url() or None} if show_url else {}),
        'model': llm.model_id(),
        'analysis_version': services.analysis_version(),
        'llm_connected': connected,
        'ocr_available': reader.ocr_available(),
    }, status=200 if connected else 503)
