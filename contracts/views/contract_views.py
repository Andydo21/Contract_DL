from .http_results import request_data as _body, service_errors
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .access import api_manager_required, api_login_required
from .http_results import respond
from contracts.services import contract_operations_service

@login_required
def contract_detail(request, contract_id):
    return respond(request, contract_operations_service.contract_detail_page(contract_id, user=request.user, query=request.GET))

@api_login_required
@service_errors
def api_contract_detail(request, contract_id):
    data = _body(request) if request.method in ('PATCH', 'PUT') else None
    return respond(request, contract_operations_service.contract_detail(contract_id, user=request.user, method=request.method, query=request.GET, data=data))

@api_login_required
@service_errors
def api_contracts_trash(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)
    return respond(request, contract_operations_service.deleted_contracts(request.user))

@api_login_required
@service_errors
def api_restore_contract(request, contract_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)
    return respond(request, contract_operations_service.restore_contract(contract_id, request.user, _body(request)))

@api_login_required
@service_errors
def api_contract_history(request, contract_id):
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)
    return respond(request, contract_operations_service.contract_history(contract_id, request.user))

@api_login_required
@service_errors
def api_contracts_list(request):
    return respond(request, contract_operations_service.contracts_list(user=request.user, method=request.method, form=request.POST, uploads=request.FILES))

@api_manager_required
@service_errors
def api_create_contract(request):
    return respond(request, contract_operations_service.create_contract(user=request.user, method=request.method, form=request.POST, uploads=request.FILES))

@api_manager_required
@service_errors
def api_manual_extract_contract(request, contract_id):
    return respond(request, contract_operations_service.manual_extract_contract(contract_id, user=request.user, method=request.method, data=_body(request), form=request.POST, query=request.GET))

@api_login_required
@service_errors
def api_contract_versions(request, contract_id):
    return respond(request, contract_operations_service.contract_versions(contract_id, user=request.user, method=request.method, form=request.POST, uploads=request.FILES))


@api_login_required
@service_errors
def api_contract_parties(request, contract_id):
    from contracts.services import party_tag_service
    from .http_results import request_data
    return respond(request, party_tag_service.contract_parties(contract_id, request.user, request.method, request_data(request)))


@api_login_required
@service_errors
def api_contract_tags(request, contract_id):
    from contracts.services import party_tag_service
    from .http_results import request_data
    return respond(request, party_tag_service.contract_tags(contract_id, request.user, request.method, request_data(request)))
