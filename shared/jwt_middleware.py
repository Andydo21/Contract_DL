"""
Shared JWT validation for all RiskDL services.
Single source of truth — mounted into every container via Docker volume.

Django services: register JWTMiddleware (and optionally JWTUserMiddleware for main web) in settings.MIDDLEWARE:
    'shared.jwt_middleware.JWTMiddleware'
    'shared.jwt_middleware.JWTUserMiddleware'

FastAPI services: use fastapi_jwt_required as a Depends() dependency:
    from shared.jwt_middleware import fastapi_jwt_required
    @app.post("/endpoint")
    def endpoint(payload: dict = Depends(fastapi_jwt_required)):
        ...
"""

import os
import jwt as pyjwt
from functools import wraps
from pathlib import Path
from dotenv import load_dotenv

# Auto-load root .env (parent of the shared/ directory) to sync SECRET_KEY
shared_dir = Path(__file__).resolve().parent
env_path = shared_dir.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-default-change-me")
ALGORITHM = "HS256"


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises jwt.ExpiredSignatureError or jwt.InvalidTokenError."""
    return pyjwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def extract_bearer(auth_header: str) -> str | None:
    """Extract token string from 'Bearer <token>' header. Returns None if missing/malformed."""
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return None


# ── Django middleware ──────────────────────────────────────────────────────────

class JWTMiddleware:
    """
    Lightweight Django middleware — validates JWT and attaches payload to request.
    Does DB user lookup for the main web if the 'contracts' app is installed.
    Safe for stateless microservices without a User database.

    Sets on request:
      - jwt_payload   : dict  — full decoded token payload
      - jwt_user_id   : int   — user ID from token
      - jwt_username  : str   — username from token
      - jwt_role      : str   — role from token
      - _jwt_user     : User  — DB User object (only on main web if user exists)
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.http import JsonResponse
        from django.apps import apps

        token = extract_bearer(request.headers.get("Authorization", ""))

        if token:
            try:
                payload = decode_token(token)
                request.jwt_payload   = payload
                request.jwt_user_id   = payload.get("user_id") or payload.get("id")
                request.jwt_username  = payload.get("username", "")
                request.jwt_role      = payload.get("role", "USER")
                request._dont_enforce_csrf_checks = True

                # If contracts app is installed (main web), perform DB lookup to attach user
                if apps.is_installed("contracts"):
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    try:
                        user = User.objects.get(id=request.jwt_user_id)
                        request._jwt_user = user
                    except User.DoesNotExist:
                        return JsonResponse({"error": "User matching token ID does not exist."}, status=401)
            except pyjwt.ExpiredSignatureError:
                return JsonResponse({"error": "Token has expired."}, status=401)
            except pyjwt.InvalidTokenError as e:
                return JsonResponse({"error": f"Invalid token: {e}"}, status=401)
        else:
            request.jwt_payload   = None
            request.jwt_user_id   = None
            request.jwt_username  = ""
            request.jwt_role      = None

        return self.get_response(request)


class JWTUserMiddleware:
    """
    Restores the JWT-authenticated user onto request.user AFTER
    Django's AuthenticationMiddleware overwrites it.
    Only needed on main web service.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, "_jwt_user"):
            request.user = request._jwt_user
        return self.get_response(request)


def jwt_required(view_func):
    """Django view decorator — returns 401 if no valid JWT present."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not getattr(request, "jwt_user_id", None):
            from django.http import JsonResponse
            return JsonResponse({"error": "Authentication required."}, status=401)
        return view_func(request, *args, **kwargs)
    return wrapper


def jwt_role_required(*roles):
    """Django view decorator — returns 403 if JWT role not in allowed list."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            from django.http import JsonResponse
            if not getattr(request, "jwt_user_id", None):
                return JsonResponse({"error": "Authentication required."}, status=401)
            if request.jwt_role not in roles:
                return JsonResponse(
                    {"error": f"Forbidden. Required roles: {list(roles)}"},
                    status=403,
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ── FastAPI dependency ─────────────────────────────────────────────────────────

def fastapi_jwt_required(authorization: str = None):
    """
    FastAPI dependency for JWT validation.
    Extracts Bearer token from incoming Authorization header and returns decoded payload.
    """
    from fastapi import HTTPException, Header
    # Note: Header(None) is handled inside route definitions, but we fetch it here
    token = extract_bearer(authorization or "")
    if not token:
        raise HTTPException(status_code=401, detail="Authorization header missing or invalid.")
    try:
        return decode_token(token)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired.")
    except pyjwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


# ── Token generation helpers for inter-service communication ────────────────────

import datetime

def generate_token(user_id, username: str, role: str, expires_in_hours: int = 24) -> str:
    """Generate a JWT token signed with the shared SECRET_KEY."""
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=expires_in_hours),
        "iat": datetime.datetime.utcnow(),
    }
    return pyjwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def get_auth_header(user_id, username: str, role: str) -> dict:
    """Get request headers with JWT Bearer authorization."""
    token = generate_token(user_id, username, role)
    return {"Authorization": f"Bearer {token}"}

def get_system_auth_header() -> dict:
    """Get system-level authorization header."""
    return get_auth_header(0, "system", "ADMIN")
