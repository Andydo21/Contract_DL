from django.http import JsonResponse


class LegacyBlockchainGuard:
    """Retire unsigned, unscoped APIs; historical database rows are retained."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == '/health/':
            return self.get_response(request)
        if not getattr(request, 'jwt_payload', None):
            return JsonResponse({'error': 'Authentication required.'}, status=401)
        return JsonResponse({'error': 'Legacy API retired. Use /api/ledger/ on the contract web.'}, status=410)
