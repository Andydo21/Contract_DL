import sys
from pathlib import Path

# Add project root to sys.path to resolve shared package
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    import jwt
    from shared.jwt_middleware import decode_token, SECRET_KEY, JWTMiddleware
    print("SUCCESS: Imported jwt_middleware successfully!")
    print(f"Loaded SECRET_KEY length: {len(SECRET_KEY)}")
    print(f"SECRET_KEY starts with: {SECRET_KEY[:15]}...")

    # Create a test token
    payload = {"user_id": 42, "username": "testuser", "role": "ADMIN"}
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    print(f"Generated test token: {token[:20]}...")

    decoded = decode_token(token)
    print(f"SUCCESS: Decoded token payload: {decoded}")
    assert decoded["user_id"] == 42
    assert decoded["role"] == "ADMIN"
    print("SUCCESS: Token verification works!")

except Exception as e:
    print(f"FAILURE: {e}")
    sys.exit(1)
