"""
Authentication and authorization.

- Barbers log in via Supabase Auth (email/password) and receive a JWT.
- The frontend sends that JWT in the Authorization: Bearer <token> header.
- get_current_barber validates the token and loads the barber's profile.
  Supabase projects can sign tokens with either the legacy symmetric
  secret (HS256) or the newer asymmetric keys (ES256/RS256). This module
  supports both, picking the right verification method based on the
  token's own header.
- The admin area uses a simple secret key (ADMIN_API_KEY), since for now
  only you (the owner) access that area.
"""
import os
from fastapi import Header, HTTPException, status
import jwt
from jwt import PyJWKClient
from app.config import supabase, SUPABASE_URL, JWT_SECRET

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
_jwks_client = PyJWKClient(JWKS_URL) if SUPABASE_URL else None

def _decode_supabase_jwt(token: str) -> dict:
    """
    Decodes and validates a Supabase-issued JWT, supporting both signing
    schemes used across Supabase projects:
      - Legacy symmetric (HS256), verified with the project's JWT secret.
      - New asymmetric (ES256/RS256), verified with the public key fetched
        from the project's JWKS endpoint.

    A leeway of 60 seconds is applied to tolerate clock drift between
    this server and Supabase's auth server.
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

async def get_current_barber(authorization: str = Header(default=None)):
    """
    Validates the Supabase JWT sent by the logged-in barber and returns
    the matching record from the `barbers` table.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token.",
        )

    token = authorization.removeprefix("Bearer ").strip()
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
    Protects admin routes (barber registration and service management).
    Compares the X-Admin-Key header against the ADMIN_API_KEY env var.
    """
    if not ADMIN_API_KEY or x_admin_key != ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrator access.",
        )
    return True
