"""HTML and JSON adapters for the A3 extraction pipeline."""
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST,require_GET
from ai.ai_extract.services import layout_service

def page_errors(view):

    @wraps(view)
    def adapter(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except ObjectDoesNotExist as error:
            raise Http404('Contract version or extraction page not found.') from error
        except ValueError as error:
            return JsonResponse({'success': False, 'error': str(error)}, status=400)
    return adapter

@login_required
def summary_lab(request):
    """Test screen for the contract summary: a pasted text, an uploaded file, two versions or a stored contract."""
    from ai.ai_extract.services import summary_service
    return render(request, 'document_viewer/summary_lab.html', summary_service.summary_lab_page(request.user))

@login_required
@page_errors
def page_inspector(request, contract_id, page_number):
    return render(request, 'document_viewer/page_inspector.html', layout_service.inspect_page(
        request.user, contract_id, page_number, request.GET.get('version_id'),
        request.GET.get('graph_relation', 'all'), request.GET.get('graph_offset', '0'),request.GET.get('graph_node'),
        request.GET.get('run_id')))

@require_POST
@login_required
@page_errors
def api_run_layout_extraction(request, contract_id):
    try:
        import json
        options={}
        if request.content_type=='application/json' and request.body:
            try:body=json.loads(request.body)
            except (ValueError,UnicodeDecodeError):raise ValueError('Invalid JSON request')
            if not isinstance(body,dict):raise ValueError('Expected a JSON object')
            for key in ('force_ocr','defer_colpali'):
                if key in body:
                    if type(body[key]) is not bool:raise ValueError(key+' must be a boolean')
                    options[key]=body[key]
        return JsonResponse(layout_service.extract(request.user, contract_id,**options))
    except (ObjectDoesNotExist, ValueError):
        raise
    except Exception as error:
        from ai.ai_extract.services.contract_pipeline_service import WorkflowBusyError
        if isinstance(error,WorkflowBusyError):
            response=JsonResponse(dict(success=False,error=str(error),code='workflow_busy'),status=409)
            response['Retry-After']='5'
            return response
        return JsonResponse({'success': False, 'error': str(error)}, status=500)


@require_POST
@login_required
@page_errors
def api_resolve_entities(request, contract_id):
    return JsonResponse(layout_service.queue_identity(request.user,contract_id),status=202)


@require_GET
@login_required
@page_errors
def api_extraction_status(request,contract_id):
    return JsonResponse(layout_service.extraction_status(request.user,contract_id))


@require_POST
@login_required
@page_errors
def api_reset_graph(request,contract_id):
    from ai.ai_extract.services.contract_pipeline_service import WorkflowBusyError
    try:return JsonResponse(layout_service.reset_graph(request.user,contract_id))
    except WorkflowBusyError as error:
        return JsonResponse(dict(success=False,error=str(error),code='workflow_busy'),status=409)


def bulk_payload(job):
    """What the dashboard shows of a bulk job; the process id and owner stay on the server."""
    if job is None:
        return dict(success=True, job=None)
    return dict(success=True, job={k: job[k] for k in ('id', 'mode', 'status', 'items', 'done', 'error', 'created_at', 'updated_at') if k in job})


@require_POST
@login_required
@page_errors
def api_start_bulk(request):
    import json
    from django.core.exceptions import PermissionDenied
    from ai.ai_extract.services import bulk_service
    try:
        body = json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError):
        raise ValueError('Invalid JSON request')
    if not isinstance(body, dict):
        raise ValueError('Expected a JSON object')
    try:
        job = bulk_service.start(request.user, body.get('contract_ids'), body.get('mode'))
    except PermissionDenied as error:
        return JsonResponse(dict(success=False, error=str(error)), status=403)
    return JsonResponse(bulk_payload(job), status=202)


@require_GET
@login_required
@page_errors
def api_bulk_status(request, job_id=None):
    from ai.ai_extract.services import bulk_service
    if job_id is None:
        return JsonResponse(bulk_payload(bulk_service.active_job() or bulk_service.latest_job(request.user)))
    job = bulk_service.read_job(job_id)
    if job.get('user_id') != request.user.pk and not request.user.is_superuser:
        raise Http404('Bulk job not found')
    return JsonResponse(bulk_payload(job))
