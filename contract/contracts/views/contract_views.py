from django.shortcuts import render
from contract.core.views.http_results import service_errors
from django.contrib.auth.decorators import login_required
from contract.core.views.access import api_manager_required, api_login_required
from contract.core.views.http_results import respond
from contract.contracts.services import contract_operations_service

@login_required
def contract_detail(request, contract_id):
    return respond(request, contract_operations_service.contract_detail_page(contract_id, user=request.user, query=request.GET))

@api_login_required
@service_errors
def api_contract_detail(request, contract_id):
    return respond(request, contract_operations_service.contract_detail(contract_id, user=request.user, method=request.method, query=request.GET))

@api_login_required
@service_errors
def api_contracts_list(request):
    return respond(request, contract_operations_service.contracts_list(user=request.user, method=request.method, form=request.POST, uploads=request.FILES))

@api_manager_required
@service_errors
def api_create_contract(request):
    return respond(request, contract_operations_service.create_contract(user=request.user, method=request.method, form=request.POST, uploads=request.FILES))

@api_login_required
@service_errors
def api_contract_versions(request, contract_id):
    return respond(request, contract_operations_service.contract_versions(contract_id, user=request.user, method=request.method, form=request.POST, uploads=request.FILES))


@api_login_required
@service_errors
def api_contract_parties(request, contract_id):
    from contract.contracts.services import party_tag_service
    from contract.core.views.http_results import request_data
    return respond(request, party_tag_service.contract_parties(contract_id, request.user, request.method, request_data(request)))


@api_login_required
@service_errors
def api_contract_tags(request, contract_id):
    from contract.contracts.services import party_tag_service
    from contract.core.views.http_results import request_data
    return respond(request, party_tag_service.contract_tags(contract_id, request.user, request.method, request_data(request)))


@api_login_required
@service_errors
def api_contract_legal(request, contract_id):
    from contract.contracts.services import legal_mark_service
    from contract.core.views.http_results import request_data
    return respond(request, legal_mark_service.contract_legal(contract_id, request.user, request.method, request_data(request)))


@login_required
def dashboard(request):
    """Render the dashboard SPA template."""
    return render(request, 'contracts/dashboard.html')
