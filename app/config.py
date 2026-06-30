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

# ---------- Application / security ----------
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

# Comma-separated origins allowed to call the API from a browser.
_raw_cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "*")
CORS_ALLOWED_ORIGINS = [o.strip() for o in _raw_cors_origins.split(",") if o.strip()]

if CORS_ALLOWED_ORIGINS == ["*"]:
    logger.warning(
        "CORS_ALLOWED_ORIGINS is set to '*' (any origin allowed). "
        "Set this to your real domain(s) before deploying to production."
    )

# Cloudflare origin protection
# Set CLOUDFLARE_ORIGIN_SECRET to a random 32-char string (same value
# configured in Cloudflare Transform Rules as X-Origin-Secret header).
CLOUDFLARE_ORIGIN_SECRET = os.getenv("CLOUDFLARE_ORIGIN_SECRET", "")
ENFORCE_CLOUDFLARE_ORIGIN = os.getenv("ENFORCE_CLOUDFLARE_ORIGIN", "false").lower() == "true"

# Toggle for verbose request/error logging.
DEBUG_LOGGING = os.getenv("DEBUG_LOGGING", "false").lower() in ("1", "true", "yes")

# ---------- Rate limiting ----------
RATE_LIMIT_BOOKING = os.getenv("RATE_LIMIT_BOOKING", "5/minute")
RATE_LIMIT_LOOKUP = os.getenv("RATE_LIMIT_LOOKUP", "10/minute")
RATE_LIMIT_LOGIN = os.getenv("RATE_LIMIT_LOGIN", "10/minute")
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "60/minute")
