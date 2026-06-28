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
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")  # used to validate the barber's token

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in the .env file"
    )

# "Admin" client: uses the service role key, bypasses RLS.
# This is the client used by the backend for all database operations.
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# ---------- Application / security settings ----------

# Comma-separated list of origins allowed to call the API from a browser,
# e.g. "https://mybarbershop.com,https://www.mybarbershop.com".
# Defaults to "*" (any origin) for local development convenience, but
# should be tightened to your real domain(s) in production.
_raw_cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "*")
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in _raw_cors_origins.split(",") if origin.strip()]

if CORS_ALLOWED_ORIGINS == ["*"]:
    logger.warning(
        "CORS_ALLOWED_ORIGINS is set to '*' (any origin allowed). "
        "Set this to your real domain(s) before deploying to production."
    )

# Toggle for verbose request/error logging. Defaults to "false" so
# production logs stay clean; set to "true" locally while debugging.
DEBUG_LOGGING = os.getenv("DEBUG_LOGGING", "false").lower() in ("1", "true", "yes")

# Rate limiting defaults (requests per time window). Can be overridden
# per-environment without touching code.
RATE_LIMIT_BOOKING = os.getenv("RATE_LIMIT_BOOKING", "5/minute")
RATE_LIMIT_LOOKUP = os.getenv("RATE_LIMIT_LOOKUP", "10/minute")
RATE_LIMIT_LOGIN = os.getenv("RATE_LIMIT_LOGIN", "10/minute")
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "60/minute")
