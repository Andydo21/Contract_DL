"""The AI service's internal endpoints (container riskdl_ai): the web container hands model calls and searches here.

Only a process started with AI_SERVICE_ROLE=ai answers, and only with the shared token; everywhere else these paths
do not exist.
"""
import hmac
import json

from django.conf import settings
from django.http import Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


def error_body(error):
    """Enough to raise the same exception class again on the web side."""
    from ai_extract.services.contract_pipeline_service import QwenContextLimitError
    if isinstance(error, QwenContextLimitError):
        args = [error.capacity, error.prompt_tokens, error.output_tokens]
    else:
        args = [str(a) if not isinstance(a, (int, float, str, type(None))) else a for a in error.args]
    return dict(type=type(error).__name__, message=str(error), args=args, status=getattr(error, 'status', None))


def internal(view):
    @csrf_exempt
    @require_POST
    def wrapped(request):
        token = getattr(settings, 'AI_SERVICE_TOKEN', '')
        if getattr(settings, 'AI_SERVICE_ROLE', 'web') != 'ai' or not token:
            raise Http404()
        if not hmac.compare_digest(request.headers.get('X-AI-Token', ''), token):
            return JsonResponse(dict(error=dict(type='PermissionError', message='Invalid AI service token')), status=403)
        try:
            return JsonResponse(dict(result=view(json.loads(request.body or b'{}'))))
        except Exception as error:  # reported to the web side, which raises it again by type
            return JsonResponse(dict(error=error_body(error)), status=502)
    return wrapped


@internal
def qwen(data):
    from ai_extract.services.contract_pipeline_service import request_qwen
    return request_qwen(data['task'], data['payload'])


@internal
def knowledge_search(data):
    from ai_extract.repositories import layout_repository
    from NewIdea.services.knowledge_search_service import search_knowledge
    user = layout_repository.user_by_id(data['user_id'])
    return search_knowledge(user, data['query'], generate=data.get('generate') is True, corpus=data.get('corpus', 'knowledge'))
