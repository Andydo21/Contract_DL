"""Authenticated JSON lookups into the legal corpus."""
from datetime import date
from functools import wraps

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

from .services import search_service as corpus


def legal_api(view):

    @require_GET
    @wraps(view)
    def adapter(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required.'}, status=401)
        try:
            result = view(request, *args, **kwargs)
            return result if isinstance(result, HttpResponse) else JsonResponse(result)
        except ValueError as error:
            return JsonResponse({'error': str(error)}, status=400)
    return adapter


def _on(request):
    value = request.GET.get('date')
    return date.fromisoformat(value) if value else None


@legal_api
def api_search(request):
    query = request.GET.get('q', '').strip()
    if not query:
        raise ValueError('q is required.')
    limit = max(1, min(30, int(request.GET.get('limit', 8))))
    return {'results': corpus.search(query, _on(request), request.GET.get('domain', 'labour'), limit)}


@legal_api
def api_article(request):
    number, article = request.GET.get('doc', ''), request.GET.get('article', '')
    if not number or not article:
        raise ValueError('doc and article are required.')
    found = corpus.article(number, article, _on(request))
    if found is None:
        return JsonResponse({'error': f'Điều {article} của {number} không có trong kho.'}, status=404)
    return found


@legal_api
def api_documents(request):
    return {'documents': corpus.documents(request.GET.get('domain', 'labour'), _on(request))}
