from django.http import JsonResponse

def _get_headers(request=None):
    from shared.jwt_middleware import get_auth_header, get_system_auth_header
    if request and hasattr(request, 'user') and request.user.is_authenticated:
        role = getattr(request.user.role, 'role_name', 'USER') if hasattr(request.user, 'role') and request.user.role else 'USER'
        return get_auth_header(request.user.id, request.user.username, role)
    return get_system_auth_header()

def _requires_manager(unauthenticated, denied):
    """A view decorator: 401 for a visitor, 403 for a user who is not a manager."""
    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            from contract.core.services.access_service import is_manager
            if not request.user.is_authenticated:
                return JsonResponse({'error': unauthenticated}, status=401)
            if not is_manager(request.user):
                return JsonResponse({'error': denied}, status=403)
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


manager_required = _requires_manager('Authentication required.', 'Permission Denied: Manager role required.')
api_manager_required = _requires_manager('Unauthorized. Please log in.',
                                         'Permission Denied: Only Managers can access this resource.')


def api_login_required(view_func):

    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Unauthorized. Please log in.'}, status=401)
        return view_func(request, *args, **kwargs)
    return _wrapped_view

