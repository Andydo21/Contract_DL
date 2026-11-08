"""The web container's side of the AI service (container riskdl_ai).

The web container answers pages and API requests; model calls (Qwen) and long jobs (extraction, risk analysis,
knowledge search) run in the AI service, which shares the database and media files. A call is a JSON POST to
/internal/ai/<name>/ with a shared token; the AI container runs the same function locally.
"""
import json

import requests
from django.conf import settings


def delegated():
    """Whether this process hands AI work to the AI service (the web container), rather than running it itself."""
    return bool(getattr(settings, 'AI_SERVICE_URL', '')) and getattr(settings, 'AI_SERVICE_ROLE', 'web') != 'ai'


def is_ai_service():
    return getattr(settings, 'AI_SERVICE_ROLE', 'web') == 'ai'


class AIServiceError(RuntimeError):
    pass


def call(name, payload, timeout=None):
    """POST to the AI service; an error it reports is raised again here with its own class when known."""
    try:
        response = requests.post(f'{settings.AI_SERVICE_URL}/internal/ai/{name}/', data=json.dumps(payload, ensure_ascii=False, default=str),
                                 headers={'Content-Type': 'application/json', 'X-AI-Token': settings.AI_SERVICE_TOKEN},
                                 timeout=timeout or settings.AI_SERVICE_TIMEOUT)
    except requests.RequestException as error:
        raise AIServiceError(f'AI service unreachable: {type(error).__name__}') from error
    try:
        body = response.json()
    except ValueError:
        raise AIServiceError(f'AI service answered HTTP {response.status_code} without JSON')
    if response.ok and 'error' not in body:
        return body['result']
    raise rebuild(body.get('error') or dict(type='AIServiceError', message=f'HTTP {response.status_code}'))


def rebuild(error):
    """The exception the AI service raised, as the caller's own class (callers catch Qwen errors by type)."""
    from ai_extract.services import contract_pipeline_service as qwen
    from NewIdea.services.errors import KnowledgeError
    known = {cls.__name__: cls for cls in (qwen.QwenGatewayError, qwen.QwenServerError, qwen.QwenContextLimitError,
                                           qwen.QwenIncompleteAnswerError, ValueError, PermissionError)}
    if error.get('type') == 'KnowledgeError':
        return KnowledgeError(error.get('message', ''), error.get('status', 400))
    cls = known.get(error.get('type'))
    if cls is None:
        return AIServiceError(error.get('message', 'AI service error'))
    try:
        return cls(*error.get('args', [error.get('message', '')]))
    except TypeError:
        return qwen.QwenGatewayError(error.get('message', ''))
