import requests
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponse, JsonResponse

from shared.jwt_middleware import get_user_auth_header

# The backend sees only the signed-in user's token, never browser credentials.
UNFORWARDED_HEADERS = {"host", "content-length", "cookie", "authorization"}


def proxy_to_workflow(request, path=""):
    """
    Reverse proxy that forwards workflow UI and API requests from the main Django
    app to workflow_service under the signed-in user's own identity.
    """
    if not request.user.is_authenticated:
        if request.method == "GET" and "application/json" not in request.headers.get("Accept", ""):
            return redirect_to_login(request.get_full_path())
        return JsonResponse({"error": "Authentication required."}, status=401)

    backend = settings.WORKFLOW_SERVICE_URL.rstrip("/")
    target_url = f"{backend}/{path.lstrip('/')}"
    if request.META.get("QUERY_STRING"):
        target_url += f"?{request.META['QUERY_STRING']}"

    headers = {k: v for k, v in request.headers.items() if k.lower() not in UNFORWARDED_HEADERS}
    headers.update(get_user_auth_header(request.user))

    try:
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=request.body,
            allow_redirects=False,
            timeout=30,
        )
    except requests.RequestException:
        return HttpResponse(
            "<div style='font-family:sans-serif;padding:32px;color:#ef4444;background:#18181b;border-radius:8px;max-width:600px;margin:40px auto;'>"
            "<h2>Workflow Service Chưa Bật</h2>"
            "<p>Không thể kết nối tới dịch vụ Workflow.</p></div>",
            status=502,
        )
    response = HttpResponse(
        content=resp.content,
        status=resp.status_code,
        content_type=resp.headers.get("Content-Type", "text/html"),
    )
    if "Location" in resp.headers:
        response["Location"] = resp.headers["Location"].replace(backend, "")
    return response
