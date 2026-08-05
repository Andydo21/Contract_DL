class JWTAuthenticationMiddleware:
    """
    Middleware that authenticates requests using JWT tokens in the Authorization header.
    Acts as an API Gateway authenticating incoming REST requests.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        import jwt
        from django.conf import settings
        from django.contrib.auth import get_user_model
        from django.http import JsonResponse

        auth_header = request.headers.get('Authorization')
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == 'bearer':
                token = parts[1]
                try:
                    # Decode JWT token using Django's SECRET_KEY
                    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
                    
                    # Retrieve user_id or id from payload
                    user_id = payload.get('user_id') or payload.get('id')
                    if not user_id:
                        return JsonResponse({'error': 'Invalid token payload: missing user ID.'}, status=401)
                    
                    User = get_user_model()
                    try:
                        user = User.objects.get(id=user_id)
                        # Store in request for later use (restored by JWTUserMiddleware after AuthenticationMiddleware runs)
                        request._jwt_user = user
                        # Bypass CSRF checks for stateless JWT-authenticated requests
                        request._dont_enforce_csrf_checks = True
                    except User.DoesNotExist:
                        return JsonResponse({'error': 'User matching token ID does not exist.'}, status=401)
                        
                except jwt.ExpiredSignatureError:
                    return JsonResponse({'error': 'Token has expired.'}, status=401)
                except jwt.InvalidTokenError as e:
                    return JsonResponse({'error': f'Invalid token: {str(e)}'}, status=401)

        return self.get_response(request)


class JWTUserMiddleware:
    """
    Restores the JWT-authenticated user onto request.user after Django's AuthenticationMiddleware runs.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, '_jwt_user'):
            request.user = request._jwt_user
        return self.get_response(request)
