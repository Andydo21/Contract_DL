from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from contract.core.views.http_results import request_data as _body, service_errors
from contract.core.views.access import _get_headers, api_login_required, api_manager_required
from contract.core.views.http_results import respond
from contract.accounts.services import identity_service

@api_manager_required
@service_errors
def api_register_company(request):
    return respond(request, identity_service.register_company(method=request.method, data=_body(request), authorization_headers=_get_headers(request)))

@api_manager_required
@service_errors
def api_register_user(request):
    return respond(request, identity_service.register_user(user=request.user, method=request.method, data=_body(request), authorization_headers=_get_headers(request)))

@api_login_required
@service_errors
def api_companies_list(request):
    return respond(request, identity_service.companies_list(data=_body(request), user=request.user))

@api_login_required
@service_errors
def api_users_list(request):
    return respond(request, identity_service.users_list(data=_body(request), user=request.user))

@api_login_required
@service_errors
def api_roles_list(request):
    return respond(request, identity_service.roles_list(data=_body(request)))


@login_required(login_url='/login/')
def identity_registry(request):
    """Render the identity registry page."""
    return render(request, 'accounts/identity_registry.html')
