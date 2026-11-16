from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from contract.core.views.http_results import request_data as _body, service_errors
from contract.core.views.access import api_manager_required, api_login_required
from contract.core.views.http_results import respond
from contract.approvals.services import workflow_gateway_service

@api_manager_required
@service_errors
def api_push_to_workflow(request, contract_id):
    return respond(request, workflow_gateway_service.push_to_workflow(contract_id, user=request.user, method=request.method, data=_body(request), query=request.GET))

@api_login_required
@service_errors
def api_workflow_status(request, contract_id):
    return respond(request, workflow_gateway_service.workflow_status(contract_id, user=request.user, method=request.method, query=request.GET))


@login_required
def workflow_board(request):
    """Chuyển hướng người dùng sang Workflow Board UI của microservice workflow_service."""
    import os
    from django.conf import settings
    wf_url = getattr(settings, 'WORKFLOW_SERVICE_PUBLIC_URL', os.environ.get('WORKFLOW_SERVICE_PUBLIC_URL', 'http://localhost:8003'))
    return redirect(f"{wf_url.rstrip('/')}/board/")
