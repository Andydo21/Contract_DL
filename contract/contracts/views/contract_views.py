from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from contract.contracts.services import contract_operations_service, legal_mark_service, party_tag_service
from contract.core.views.access import api_login_required, api_manager_required
from contract.core.views.http_results import request_data as _body, respond, service_errors


def _allow(*methods):
    """Answer 405 (JSON for the API) before anything else for a method the endpoint does not take."""
    return require_http_methods(list(methods))


@login_required
def contract_detail(request, contract_id):
    return respond(request, contract_operations_service.contract_detail_page(contract_id, user=request.user, query=request.GET))


@_allow('GET', 'PATCH', 'PUT', 'DELETE')
@api_login_required
@service_errors
def api_contract_detail(request, contract_id):
    data = _body(request) if request.method in ('PATCH', 'PUT') else None
    return respond(request, contract_operations_service.contract_detail(contract_id, user=request.user, method=request.method, query=request.GET, data=data))


@_allow('GET')
@api_login_required
@service_errors
def api_contracts_trash(request):
    return respond(request, contract_operations_service.deleted_contracts(request.user))


@_allow('POST')
@api_login_required
@service_errors
def api_restore_contract(request, contract_id):
    return respond(request, contract_operations_service.restore_contract(contract_id, request.user, _body(request)))


@_allow('DELETE')
@api_login_required
@service_errors
def api_purge_contract(request, contract_id):
    """DELETE: remove a contract in the trash for good (managers only)."""
    return respond(request, contract_operations_service.purge_contract(contract_id, request.user))


@_allow('GET')
@api_login_required
@service_errors
def api_contract_history(request, contract_id):
    return respond(request, contract_operations_service.contract_history(contract_id, request.user))


@_allow('GET', 'POST')
@api_login_required
@service_errors
def api_contracts_list(request):
    return respond(request, contract_operations_service.contracts_list(user=request.user, method=request.method, form=request.POST,
                                                                       uploads=request.FILES, query=request.GET))


@_allow('POST')
@api_manager_required
@service_errors
def api_create_contract(request):
    return respond(request, contract_operations_service.create_contract(user=request.user, method=request.method, form=request.POST, uploads=request.FILES))


@_allow('GET', 'POST')
@api_login_required
@service_errors
def api_contract_versions(request, contract_id):
    return respond(request, contract_operations_service.contract_versions(contract_id, user=request.user, method=request.method, form=request.POST, uploads=request.FILES))


@api_login_required
@service_errors
def api_contract_parties(request, contract_id):
    return respond(request, party_tag_service.contract_parties(contract_id, request.user, request.method, _body(request)))


@api_login_required
@service_errors
def api_contract_tags(request, contract_id):
    return respond(request, party_tag_service.contract_tags(contract_id, request.user, request.method, _body(request)))


@api_login_required
@service_errors
def api_contract_legal(request, contract_id):
    return respond(request, legal_mark_service.contract_legal(contract_id, request.user, request.method, _body(request)))


@login_required
def dashboard(request):
    """Render the dashboard SPA template."""
    return render(request, 'contracts/dashboard.html')
