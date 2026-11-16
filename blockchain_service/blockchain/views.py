from django.http import JsonResponse
from .repositories import BookRepository as repo

def health_check(request):
    import os
    import requests
    database_ok = False
    fabric_ok = False
    try:
        repo.ping()
        database_ok = True
    except Exception:
        pass
    try:
        response = requests.get(os.getenv('FABRIC_GATEWAY_URL', 'http://localhost:5000') + '/health', timeout=7)
        fabric_ok = response.ok and response.json().get('status') == 'healthy'
    except (requests.RequestException, ValueError):
        pass
    healthy = database_ok and fabric_ok
    return JsonResponse({"status": "healthy" if healthy else "degraded",
        "service": "blockchain-django-service", "database_connected": database_ok,
        "fabric_connected": fabric_ok}, status=200 if healthy else 503)
