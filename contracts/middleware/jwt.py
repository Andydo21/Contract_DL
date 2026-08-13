import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import JsonResponse


class JWTAuthenticationMiddleware:
    """
    Validates JWT Bearer tokens on incoming API requests.
    Position in MIDDLEWARE: BEFORE AuthenticationMiddleware.

    If a valid token is found:
      - Looks up the user in DB
      - Sets request._jwt_user for JWTUserMiddleware to restore later
      - Bypasses CSRF for stateless JWT requests

    If no Authorization header: passes through (session auth still works normally).
    If token is invalid/expired: returns 401 immediately.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        auth_header = request.headers.get("Authorization", "")

        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            try:
                payload = jwt.decode(
                    token,
                    settings.SECRET_KEY,
                    algorithms=["HS256"],
                )

                user_id = payload.get("user_id") or payload.get("id")
                if not user_id:
                    return JsonResponse(
                        {"error": "Invalid token payload: missing user ID."},
                        status=401,
                    )

                User = get_user_model()
                try:
                    user = User.objects.get(id=user_id)
                    request._jwt_user = user
                    request._dont_enforce_csrf_checks = True
                except User.DoesNotExist:
                    return JsonResponse(
                        {"error": "User matching token ID does not exist."},
                        status=401,
                    )

            except jwt.ExpiredSignatureError:
                return JsonResponse({"error": "Token has expired."}, status=401)
            except jwt.InvalidTokenError as e:
                return JsonResponse({"error": f"Invalid token: {str(e)}"}, status=401)

        return self.get_response(request)


class JWTUserMiddleware:
    """
    Restores the JWT-authenticated user onto request.user AFTER
    Django's AuthenticationMiddleware overwrites it.

    Position in MIDDLEWARE: AFTER AuthenticationMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, "_jwt_user"):
            request.user = request._jwt_user
        return self.get_response(request)
