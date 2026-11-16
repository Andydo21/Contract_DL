from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from contract.core.views.access import manager_required
from contract.core.views.http_results import request_data as _body, service_errors
from contract.core.views.access import _get_headers, api_manager_required
from contract.core.views.http_results import respond
from contract.administration.services import administration_service

@api_manager_required
@service_errors
def api_admin_stats(request):
    return respond(request, administration_service.admin_stats(query=request.GET))

@api_manager_required
@service_errors
def api_admin_delete_user(request, user_id):
    return respond(request, administration_service.admin_delete_user(user_id, user=request.user))

@api_manager_required
@service_errors
def api_admin_retry_user(request, user_id):
    return respond(request, administration_service.admin_retry_user(user_id, user=request.user, data=_body(request), authorization_headers=_get_headers(request)))

@api_manager_required
@service_errors
def api_admin_toggle_ocr(request):
    return respond(request, administration_service.admin_toggle_ocr(user=request.user, method=request.method, data=_body(request), metadata=request.META))


@ensure_csrf_cookie  # the page's switches post with the token from this cookie
@manager_required
def admin_dashboard(request):
    """Render the custom Admin Dashboard."""
    return render(request, 'administration/admin_dashboard.html')


@api_manager_required
@service_errors
def api_admin_legal_documents(request):
    return respond(request, administration_service.admin_legal_documents(user=request.user))


@api_manager_required
@service_errors
def api_admin_switch_legal(request, document_id):
    if request.method != 'POST':
        from django.http import JsonResponse
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    return respond(request, administration_service.admin_switch_legal(document_id, user=request.user, data=_body(request),
                                                                      metadata=request.META))
