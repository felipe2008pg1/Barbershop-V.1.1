"""
MFA (TOTP) helpers built on Supabase Auth's native MFA support.

Supabase's MFA endpoints (enroll/challenge/verify) operate on the
*caller's* session, not the service-role key. Each call here builds a
short-lived client scoped to the barber's own access token so the
service-role key is never used for MFA operations.
"""
from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_ANON_KEY


def user_scoped_client(access_token: str, refresh_token: str) -> Client:
    if not SUPABASE_ANON_KEY:
        raise RuntimeError("SUPABASE_ANON_KEY is not configured.")
    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    client.auth.set_session(access_token, refresh_token)
    return client


def has_verified_factor(access_token: str, refresh_token: str) -> bool:
    client = user_scoped_client(access_token, refresh_token)
    factors = client.auth.mfa.list_factors()
    all_factors = (factors.totp or []) if factors else []
    return any(f.status == "verified" for f in all_factors)
