"""Ledger-book endpoints, called by the contract web with the shared service token (LEDGER_BOOK_TOKEN)."""
import hmac
import json
import os

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import book


def token_ok(request):
    expected = os.environ.get('LEDGER_BOOK_TOKEN', '')
    return bool(expected) and hmac.compare_digest(request.headers.get('X-Ledger-Book-Token', ''), expected)


def endpoint(action):
    @csrf_exempt
    @require_POST
    def view(request):
        if not token_ok(request):
            return JsonResponse({'error': 'Service authentication required'}, status=401)
        try:
            return JsonResponse(dict(status='success', **action(json.loads(request.body))))
        except (KeyError, ValueError, TypeError) as error:
            return JsonResponse({'error': f'{type(error).__name__}: {error}'}, status=400)
    return view


record_operation = endpoint(book.record_operation)
record_verification = endpoint(book.record_verification)
record_credential = endpoint(book.record_credential)
register_user = endpoint(book.register_user)
