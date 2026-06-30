"""
Authentication and authorization.

JWT is read preferentially from the HttpOnly cookie set at login.
Falls back to Authorization: Bearer header for API clients / testing.
"""
import os
from fastapi import Cookie, Header, HTTPException, Request, status
import jwt
from jwt import PyJWKClient
from app.config import supabase, SUPABASE_URL, JWT_SECRET

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
_jwks_client = PyJWKClient(JWKS_URL) if SUPABASE_URL else None
_COOKIE_NAME = "barber_session"


def _decode_supabase_jwt(token: str) -> dict:
    """
    Decodes and validates a Supabase-issued JWT.
    Supports HS256 (legacy) and ES256/RS256 (asymmetric).
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Malformed token.")

    algorithm = unverified_header.get("alg", "HS256")

    try:
        if algorithm == "HS256":
            if not JWT_SECRET:
                raise HTTPException(
                    status_code=500,
                    detail="Server misconfiguration: SUPABASE_JWT_SECRET is not set.",
                )
            return jwt.decode(
                token,
                JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
                leeway=60,
            )
        else:
            if not _jwks_client:
                raise HTTPException(
                    status_code=500,
                    detail="Server misconfiguration: SUPABASE_URL is not set.",
                )
            signing_key = _jwks_client.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=[algorithm],
                audience="authenticated",
                leeway=60,
            )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )


def _extract_token(request: Request) -> str:
    """
    Extracts the JWT from:
    1. HttpOnly cookie (preferred — set by /login)
    2. Authorization: Bearer header (fallback for API clients)
    """
    # Cookie takes priority — set by our login endpoint
    cookie_token = request.cookies.get(_COOKIE_NAME)
    if cookie_token:
        return cookie_token

    # Fallback: Authorization header
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing authentication token.",
    )


async def get_current_barber(request: Request):
    """
    Validates the JWT (from cookie or header) and returns the barber's profile.
    """
    token = _extract_token(request)
    payload = _decode_supabase_jwt(token)

    barber_id = payload.get("sub")
    if not barber_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    result = (
        supabase.table("barbers")
        .select("*")
        .eq("id", barber_id)
        .eq("active", True)
        .maybe_single()
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Barber not found or inactive.",
        )

    return result.data


def require_admin(x_admin_key: str = Header(default=None)):
    """
    Protects admin routes via X-Admin-Key header.
    Uses constant-time comparison to prevent timing attacks.
    """
    import hmac
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=500, detail="Server misconfiguration.")
    if not x_admin_key or not hmac.compare_digest(x_admin_key, ADMIN_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrator access.",
        )
    return True
