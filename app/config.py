"""
Central application configuration.
Loads environment variables once and exposes typed, validated settings
plus the configured Supabase client used throughout the app.
"""
import logging
import os
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()
logger = logging.getLogger("barbershop.config")

# ---------- Supabase ----------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in the .env file"
    )

# "Admin" client: uses the service role key, bypasses RLS.
# NEVER expose this client to user-facing routes without explicit filters.
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# Public client: uses the anon key, respects RLS. Use this for any
# read/write that should be limited to what an unauthenticated caller
# is allowed to see per the public_read_active_* / public_insert_*
# policies — e.g. listing active barbers/services. Built lazily so a
# missing SUPABASE_ANON_KEY only breaks the routes that actually need it.
_anon_client: Client | None = None


def get_anon_client() -> Client:
    global _anon_client
    if _anon_client is None:
        if not SUPABASE_ANON_KEY:
            raise RuntimeError("SUPABASE_ANON_KEY is not configured.")
        _anon_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return _anon_client

# ---------- Field-level encryption ----------
# Fail fast at startup rather than at the first encrypted write/read —
# a missing key here would otherwise surface as a confusing 500 deep
# inside a request.
if not os.getenv("DATA_ENCRYPTION_KEY"):
    raise RuntimeError(
        "DATA_ENCRYPTION_KEY must be set. Generate one with: "
        "python -c \"import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())\""
    )
if not os.getenv("DATA_BLIND_INDEX_KEY"):
    raise RuntimeError(
        "DATA_BLIND_INDEX_KEY must be set. Generate one with: "
        "python -c \"import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())\""
    )

# ---------- Application / security ----------
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

_raw_cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "*")
CORS_ALLOWED_ORIGINS = [o.strip() for o in _raw_cors_origins.split(",") if o.strip()]
if CORS_ALLOWED_ORIGINS == ["*"]:
    logger.warning(
        "CORS_ALLOWED_ORIGINS is set to '*' (any origin allowed). "
        "Set this to your real domain(s) before deploying to production."
    )

CLOUDFLARE_ORIGIN_SECRET = os.getenv("CLOUDFLARE_ORIGIN_SECRET", "")
ENFORCE_CLOUDFLARE_ORIGIN = os.getenv("ENFORCE_CLOUDFLARE_ORIGIN", "false").lower() == "true"

DEBUG_LOGGING = os.getenv("DEBUG_LOGGING", "false").lower() in ("1", "true", "yes")

# ---------- Rate limiting ----------
RATE_LIMIT_BOOKING = os.getenv("RATE_LIMIT_BOOKING", "5/minute")
RATE_LIMIT_LOOKUP = os.getenv("RATE_LIMIT_LOOKUP", "10/minute")
RATE_LIMIT_LOGIN = os.getenv("RATE_LIMIT_LOGIN", "10/minute")
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "60/minute")
