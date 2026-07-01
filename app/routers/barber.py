"""
Barber area routes (requires login via Supabase Auth).
"""
import logging
from datetime import date as date_type
from typing import Optional
from fastapi import APIRouter, Cookie, HTTPException, Depends, Query, Request, Response
from app.service_translations import translate_service_name
from app.config import supabase, ENVIRONMENT
from app.auth import get_current_barber, get_barber_db
from app.models import (
    AppointmentUpdate,
    ScheduleSlot,
    TimeOffCreate,
    BarberLogin,
    MFAEnrollVerify,
    MFALoginVerify,
    MFAUnenroll,
    ChangePasswordRequest,
)
from app.rate_limit import limiter
from app.security.login_guard import login_guard
from app.security.password_policy import validate_password
from app.security.mfa import user_scoped_client
from app.security.crypto import decrypt_field


def _decrypt_barber_profile(profile: dict) -> dict:
    out = dict(profile)
    out["email"] = decrypt_field(profile.get("email_enc"))
    out["phone"] = decrypt_field(profile.get("phone_enc")) if profile.get("phone_enc") else None
    out.pop("email_enc", None)
    out.pop("email_hash", None)
    out.pop("phone_enc", None)
    return out

router = APIRouter(prefix="/api/barber", tags=["barber"])
logger = logging.getLogger("barbershop.barber")

_COOKIE_NAME = "barber_session"
_PENDING_COOKIE_NAME = "barber_mfa_pending"
_IS_PROD = ENVIRONMENT == "production"
_PENDING_MAX_AGE = 300  # 5 min to complete the second factor


def _set_session_cookie(response: Response, token: str, max_age: int = 3600) -> None:
    """
    Stores the JWT in an HttpOnly + Secure + SameSite=Strict cookie.
    Never accessible via JavaScript — eliminates XSS token theft.
    """
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=_IS_PROD,
        samesite="strict",
        path="/api/barber",
    )


def _set_pending_cookie(response: Response, access_token: str, refresh_token: str) -> None:
    """
    Holds the aal1 (password-verified, MFA-pending) tokens until the
    second factor is confirmed. Separate, short-lived, never exposed
    to JS — same hardening as the final session cookie.
    """
    response.set_cookie(
        key=_PENDING_COOKIE_NAME,
        value=f"{access_token}:{refresh_token}",
        max_age=_PENDING_MAX_AGE,
        httponly=True,
        secure=_IS_PROD,
        samesite="strict",
        path="/api/barber/mfa",
    )


def _clear_pending_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_PENDING_COOKIE_NAME,
        path="/api/barber/mfa",
        httponly=True,
        secure=_IS_PROD,
        samesite="strict",
    )


def _split_pending(pending_raw: str) -> tuple[str, str]:
    if not pending_raw or ":" not in pending_raw:
        raise HTTPException(status_code=401, detail="MFA session expired. Please log in again.")
    access_token, _, refresh_token = pending_raw.partition(":")
    if not access_token or not refresh_token:
        raise HTTPException(status_code=401, detail="MFA session expired. Please log in again.")
    return access_token, refresh_token


@router.post("/login")
@limiter.limit("10/minute")
def login(request: Request, response: Response, credentials: BarberLogin):
    """
    Authenticates the barber with email/password.

    If the account has a verified MFA factor, the full session is
    withheld: only a short-lived "pending" cookie is set, and the
    client must call /mfa/login/challenge then /mfa/login/verify to
    obtain the real session cookie. If no MFA is enrolled, login
    completes immediately (existing behavior).
    """
    client_ip = request.client.host if request.client else "unknown"

    login_guard.check(client_ip, credentials.email)

    try:
        result = supabase.auth.sign_in_with_password(
            {"email": credentials.email, "password": credentials.password}
        )
    except Exception:
        login_guard.record_failure(client_ip, credentials.email)
        logger.info("Failed login attempt for %s from %s", credentials.email, client_ip)
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if not result or not result.session:
        login_guard.record_failure(client_ip, credentials.email)
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    try:
        profile = (
            supabase.table("barbers")
            .select("*")
            .eq("id", result.user.id)
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.exception("Failed to load barber profile after login")
        raise HTTPException(status_code=503, detail="Could not complete login right now.")

    if not profile or not profile.data:
        raise HTTPException(status_code=403, detail="Barber profile not found.")

    if not profile.data.get("active"):
        raise HTTPException(status_code=403, detail="Barber account is inactive.")

    login_guard.record_success(client_ip, credentials.email)

    # Check for an enrolled, verified MFA factor on this account.
    try:
        user_client = user_scoped_client(result.session.access_token, result.session.refresh_token)
        factors = user_client.auth.mfa.list_factors()
        verified = [f for f in (factors.totp or [])] if factors else []
        verified_factors = [f for f in verified if f.status == "verified"]
    except Exception:
        logger.exception("Failed to check MFA factors for barber %s", result.user.id)
        verified_factors = []

    if verified_factors:
        # Step-up required — do NOT issue the final session cookie yet.
        _set_pending_cookie(response, result.session.access_token, result.session.refresh_token)
        logger.info("Barber %s passed password check, MFA step-up required", credentials.email)
        return {
            "mfa_required": True,
            "factor_id": verified_factors[0].id,
        }

    _set_session_cookie(
        response,
        result.session.access_token,
        max_age=result.session.expires_in or 3600,
    )
    logger.info("Barber %s logged in from %s (no MFA enrolled)", credentials.email, client_ip)
    return {"mfa_required": False, "barber": _decrypt_barber_profile(profile.data)}


@router.post("/mfa/login/challenge")
@limiter.limit("10/minute")
def mfa_login_challenge(
    request: Request,
    factor_id: str = Query(...),
    barber_mfa_pending: Optional[str] = Cookie(default=None),
):
    """Issues a TOTP challenge for the pending login. Call before /mfa/login/verify."""
    access_token, refresh_token = _split_pending(barber_mfa_pending)
    client = user_scoped_client(access_token, refresh_token)
    try:
        challenge = client.auth.mfa.challenge({"factor_id": factor_id})
    except Exception:
        logger.exception("Failed to create MFA login challenge")
        raise HTTPException(status_code=400, detail="Could not start MFA verification.")
    return {"challenge_id": challenge.id}


@router.post("/mfa/login/verify")
@limiter.limit("10/minute")
def mfa_login_verify(
    request: Request,
    response: Response,
    challenge_id: str = Query(...),
    body: MFALoginVerify = ...,
    barber_mfa_pending: Optional[str] = Cookie(default=None),
):
    """
    Verifies the TOTP code for a pending login and, on success, issues
    the real, fully-authenticated (aal2) session cookie.
    """
    client_ip = request.client.host if request.client else "unknown"
    access_token, refresh_token = _split_pending(barber_mfa_pending)
    client = user_scoped_client(access_token, refresh_token)

    try:
        verify_result = client.auth.mfa.verify(
            {"factor_id": body.factor_id, "challenge_id": challenge_id, "code": body.code}
        )
    except Exception:
        logger.info("Failed MFA code verification from %s", client_ip)
        raise HTTPException(status_code=401, detail="Invalid or expired authentication code.")

    if not verify_result or not getattr(verify_result, "access_token", None):
        raise HTTPException(status_code=401, detail="Invalid or expired authentication code.")

    try:
        profile = (
            supabase.table("barbers")
            .select("*")
            .eq("id", verify_result.user.id)
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.exception("Failed to load barber profile after MFA verify")
        raise HTTPException(status_code=503, detail="Could not complete login right now.")

    if not profile or not profile.data:
        raise HTTPException(status_code=403, detail="Barber profile not found.")

    _clear_pending_cookie(response)
    _set_session_cookie(response, verify_result.access_token, max_age=verify_result.expires_in or 3600)
    logger.info("Barber %s completed MFA login from %s", verify_result.user.id, client_ip)
    return {"barber": _decrypt_barber_profile(profile.data)}


@router.post("/mfa/enroll")
def mfa_enroll(barber: dict = Depends(get_current_barber), request: Request = None):
    """
    Starts TOTP enrollment for the currently logged-in barber.
    Returns a QR code (SVG) and secret to scan in an authenticator app.
    """
    access_token = request.cookies.get(_COOKIE_NAME)
    if not access_token:
        raise HTTPException(status_code=401, detail="Missing session.")
    # We don't have the refresh token from the cookie (only access token is
    # stored) — Supabase's set_session accepts the same token in both slots
    # for the purpose of issuing MFA calls during an active access session.
    client = user_scoped_client(access_token, access_token)
    try:
        enroll_result = client.auth.mfa.enroll(
            {"factor_type": "totp", "friendly_name": f"barber-{barber['id'][:8]}"}
        )
    except Exception:
        logger.exception("MFA enroll failed for barber %s", barber["id"])
        raise HTTPException(status_code=400, detail="Could not start MFA enrollment.")

    totp = enroll_result.totp
    return {
        "factor_id": enroll_result.id,
        "qr_code_svg": totp.qr_code,
        "secret": totp.secret,
        "uri": totp.uri,
    }


@router.post("/mfa/enroll/verify")
def mfa_enroll_verify(
    body: MFAEnrollVerify,
    request: Request,
    barber: dict = Depends(get_current_barber),
):
    """Confirms enrollment by validating the first TOTP code from the app."""
    access_token = request.cookies.get(_COOKIE_NAME)
    if not access_token:
        raise HTTPException(status_code=401, detail="Missing session.")
    client = user_scoped_client(access_token, access_token)
    try:
        challenge = client.auth.mfa.challenge({"factor_id": body.factor_id})
        client.auth.mfa.verify(
            {"factor_id": body.factor_id, "challenge_id": challenge.id, "code": body.code}
        )
    except Exception:
        logger.info("MFA enroll verification failed for barber %s", barber["id"])
        raise HTTPException(status_code=400, detail="Invalid authentication code.")

    logger.info("MFA enrolled for barber %s", barber["id"])
    return {"detail": "MFA enabled successfully."}


@router.post("/mfa/unenroll")
def mfa_unenroll(
    body: MFAUnenroll,
    request: Request,
    barber: dict = Depends(get_current_barber),
):
    """Disables MFA — requires an active, already-authenticated session."""
    access_token = request.cookies.get(_COOKIE_NAME)
    if not access_token:
        raise HTTPException(status_code=401, detail="Missing session.")
    client = user_scoped_client(access_token, access_token)
    try:
        client.auth.mfa.unenroll({"factor_id": body.factor_id})
    except Exception:
        logger.exception("MFA unenroll failed for barber %s", barber["id"])
        raise HTTPException(status_code=400, detail="Could not disable MFA.")

    logger.info("MFA disabled for barber %s", barber["id"])
    return {"detail": "MFA disabled."}


@router.post("/logout")
def logout(response: Response, barber: dict = Depends(get_current_barber)):
    """Clears the session cookie and invalidates the Supabase session."""
    try:
        supabase.auth.sign_out()
    except Exception:
        pass

    response.delete_cookie(
        key=_COOKIE_NAME,
        path="/api/barber",
        httponly=True,
        secure=_IS_PROD,
        samesite="strict",
    )
    logger.info("Barber %s logged out", barber.get("id"))
    return {"detail": "Logged out."}


@router.post("/change-password")
def change_password(
    request: Request,
    body: ChangePasswordRequest,
    barber: dict = Depends(get_current_barber),
):
    """
    Changes the barber's password.
    Enforces the password policy (including the email-substring rule)
    before calling Supabase.
    """
    new_password = body.new_password

    validate_password(new_password, barber.get("email", ""))

    try:
        supabase.auth.update_user({"password": new_password})
    except Exception:
        logger.exception("Failed to change password for barber %s", barber.get("id"))
        raise HTTPException(status_code=503, detail="Could not change password right now.")

    logger.info("Password changed for barber %s", barber.get("id"))
    return {"detail": "Password updated successfully."}


@router.get("/me")
def get_me(barber: dict = Depends(get_current_barber)):
    return barber


@router.get("/appointments")
def list_my_appointments(
    request: Request,
    date: Optional[date_type] = Query(default=None),
    status: Optional[str] = Query(default=None),
    barber: dict = Depends(get_current_barber),
    db=Depends(get_barber_db),
):
    if status is not None and status not in {"scheduled", "completed", "cancelled"}:
        raise HTTPException(status_code=400, detail="Invalid status filter.")

    lang = (request.headers.get("X-Lang") or "pt").strip().lower()
    if lang not in ("pt", "en"):
        lang = "pt"

    try:
        query = (
            db.table("appointments")
            .select("*, services(name, price, duration_minutes)")
            .eq("barber_id", barber["id"])
        )
        if date:
            query = query.eq("date", date.isoformat())
        if status:
            query = query.eq("status", status)

        result = query.order("date").order("time").execute()
        appointments = result.data or []
        for appt in appointments:
            appt["client_phone"] = decrypt_field(appt.get("client_phone_enc"))
            appt["client_email"] = decrypt_field(appt.get("client_email_enc")) if appt.get("client_email_enc") else None
            appt.pop("client_phone_enc", None)
            appt.pop("client_phone_hash", None)
            appt.pop("client_email_enc", None)
            if appt.get("services"):
                appt["services"]["name"] = translate_service_name(appt["services"]["name"], lang)
        return appointments
    except Exception:
        logger.exception("Failed to list barber appointments")
        raise HTTPException(status_code=503, detail="Could not load appointments right now.")


@router.put("/appointments/{appointment_id}")
def update_appointment(
    appointment_id: str,
    data: AppointmentUpdate,
    barber: dict = Depends(get_current_barber),
    db=Depends(get_barber_db),
):
    from app.services.appointment_service import update_appointment_status

    payload = {k: v for k, v in data.model_dump(mode="json").items() if v is not None}
    if not payload:
        raise HTTPException(status_code=400, detail="No data to update.")

    if "status" in payload:
        if len(payload) > 1:
            raise HTTPException(
                status_code=400,
                detail="Status must be updated alone, not mixed with other fields.",
            )
        return update_appointment_status(appointment_id, payload["status"], barber, db=db)

    try:
        existing = (
            db.table("appointments")
            .select("id")
            .eq("id", appointment_id)
            .eq("barber_id", barber["id"])
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.exception("Failed to verify appointment ownership")
        raise HTTPException(status_code=503, detail="Could not update the appointment right now.")

    if not existing or not existing.data:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    try:
        result = (
            db.table("appointments")
            .update(payload)
            .eq("id", appointment_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=400, detail="Could not update the appointment.")
        logger.info(
            "Appointment %s updated fields=%s barber=%s",
            appointment_id, list(payload.keys()), barber["id"],
        )
        return result.data[0]
    except HTTPException:
        raise
    except Exception as exc:
        err = str(exc).lower()
        if "duplicate key" in err or "unique" in err:
            raise HTTPException(
                status_code=409,
                detail="This time slot has already been booked. Please choose another.",
            )
        logger.exception("Failed to update appointment=%s", appointment_id)
        raise HTTPException(status_code=503, detail="Could not update the appointment right now.")


@router.get("/schedule")
def get_schedule(barber: dict = Depends(get_current_barber), db=Depends(get_barber_db)):
    try:
        result = (
            db.table("barber_schedules")
            .select("*")
            .eq("barber_id", barber["id"])
            .order("weekday")
            .execute()
        )
        return result.data or []
    except Exception:
        logger.exception("Failed to load barber schedule")
        raise HTTPException(status_code=503, detail="Could not load schedule right now.")


@router.put("/schedule")
def set_schedule(
    slots: list[ScheduleSlot],
    barber: dict = Depends(get_current_barber),
    db=Depends(get_barber_db),
):
    weekdays = [s.weekday for s in slots]
    if len(weekdays) != len(set(weekdays)):
        raise HTTPException(status_code=400, detail="Each weekday can only appear once in the schedule.")

    try:
        db.table("barber_schedules").delete().eq("barber_id", barber["id"]).execute()
        if not slots:
            return []
        payload = [
            {**slot.model_dump(mode="json"), "barber_id": barber["id"]} for slot in slots
        ]
        result = db.table("barber_schedules").insert(payload).execute()
        logger.info("Schedule updated for barber %s (%d active days)", barber["id"], len(slots))
        return result.data or []
    except Exception:
        logger.exception("Failed to save barber schedule")
        raise HTTPException(status_code=503, detail="Could not save the schedule right now.")


@router.get("/time-off")
def list_time_off(barber: dict = Depends(get_current_barber), db=Depends(get_barber_db)):
    try:
        result = (
            db.table("barber_time_off")
            .select("*")
            .eq("barber_id", barber["id"])
            .order("date")
            .execute()
        )
        return result.data or []
    except Exception:
        logger.exception("Failed to list time off")
        raise HTTPException(status_code=503, detail="Could not load time off right now.")


@router.post("/time-off", status_code=201)
def create_time_off(
    data: TimeOffCreate,
    barber: dict = Depends(get_current_barber),
    db=Depends(get_barber_db),
):
    try:
        payload = {**data.model_dump(mode="json"), "barber_id": barber["id"]}
        result = db.table("barber_time_off").insert(payload).execute()
        if not result.data:
            raise HTTPException(status_code=400, detail="Could not create time off.")
        return result.data[0]
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to create time off")
        raise HTTPException(status_code=503, detail="Could not create time off right now.")


@router.delete("/time-off/{time_off_id}", status_code=204)
def delete_time_off(
    time_off_id: str,
    barber: dict = Depends(get_current_barber),
    db=Depends(get_barber_db),
):
    try:
        existing = (
            db.table("barber_time_off")
            .select("id")
            .eq("id", time_off_id)
            .eq("barber_id", barber["id"])
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.exception("Failed to verify time off ownership")
        raise HTTPException(status_code=503, detail="Could not delete time off right now.")

    if not existing or not existing.data:
        raise HTTPException(status_code=404, detail="Time off entry not found.")

    try:
        db.table("barber_time_off").delete().eq("id", time_off_id).execute()
    except Exception:
        logger.exception("Failed to delete time off")
        raise HTTPException(status_code=503, detail="Could not delete time off right now.")
