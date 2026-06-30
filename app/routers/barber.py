"""
Barber area routes (requires login via Supabase Auth).
"""
import logging
from typing import Optional
from fastapi import APIRouter, Cookie, HTTPException, Depends, Query, Request, Response
from app.service_translations import translate_service_name
from app.config import supabase, ENVIRONMENT
from app.auth import get_current_barber
from app.models import AppointmentUpdate, ScheduleSlot, TimeOffCreate, BarberLogin
from app.rate_limit import limiter
from app.security.login_guard import login_guard
from app.security.password_policy import validate_password

router = APIRouter(prefix="/api/barber", tags=["barber"])
logger = logging.getLogger("barbershop.barber")

_COOKIE_NAME = "barber_session"
_IS_PROD = ENVIRONMENT == "production"


def _set_session_cookie(response: Response, token: str, max_age: int = 3600) -> None:
    """
    Stores the JWT in an HttpOnly + Secure + SameSite=Strict cookie.
    Never accessible via JavaScript — eliminates XSS token theft.
    """
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        max_age=max_age,           # seconds; matches Supabase JWT TTL
        httponly=True,             # JS cannot read this cookie
        secure=_IS_PROD,           # HTTPS only in production
        samesite="strict",         # never sent on cross-site requests (CSRF protection)
        path="/api/barber",        # scoped — not sent to other routes
    )


@router.post("/login")
@limiter.limit("10/minute")
def login(request: Request, response: Response, credentials: BarberLogin):
    """
    Authenticates the barber and returns profile data.
    The JWT is stored in an HttpOnly cookie — NOT returned in the body.
    """
    client_ip = request.client.host if request.client else "unknown"

    # Lockout check — blocks IP after repeated failures
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

    # JWT goes into HttpOnly cookie — never in the response body
    _set_session_cookie(
        response,
        result.session.access_token,
        max_age=result.session.expires_in or 3600,
    )

    logger.info("Barber %s logged in from %s", credentials.email, client_ip)

    # Return profile only — token is in the cookie
    return {"barber": profile.data}


@router.post("/logout")
def logout(response: Response, barber: dict = Depends(get_current_barber)):
    """Clears the session cookie and invalidates the Supabase session."""
    try:
        supabase.auth.sign_out()
    except Exception:
        pass  # best-effort; cookie deletion is what matters client-side

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
    body: dict,
    barber: dict = Depends(get_current_barber),
):
    """
    Changes the barber's password.
    Enforces the password policy before calling Supabase.
    """
    new_password = body.get("new_password", "")

    # Validate policy — raises HTTPException on failure
    validate_password(new_password)

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
    date: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    barber: dict = Depends(get_current_barber),
):
    if status is not None and status not in {"scheduled", "completed", "cancelled"}:
        raise HTTPException(status_code=400, detail="Invalid status filter.")

    lang = (request.headers.get("X-Lang") or "pt").strip().lower()
    if lang not in ("pt", "en"):
        lang = "pt"

    try:
        query = (
            supabase.table("appointments")
            .select("*, services(name, price, duration_minutes)")
            .eq("barber_id", barber["id"])
        )
        if date:
            query = query.eq("date", date)
        if status:
            query = query.eq("status", status)

        result = query.order("date").order("time").execute()
        appointments = result.data or []
        for appt in appointments:
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
        return update_appointment_status(appointment_id, payload["status"], barber)

    try:
        existing = (
            supabase.table("appointments")
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
            supabase.table("appointments")
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
def get_schedule(barber: dict = Depends(get_current_barber)):
    try:
        result = (
            supabase.table("barber_schedules")
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
def set_schedule(slots: list[ScheduleSlot], barber: dict = Depends(get_current_barber)):
    weekdays = [s.weekday for s in slots]
    if len(weekdays) != len(set(weekdays)):
        raise HTTPException(status_code=400, detail="Each weekday can only appear once in the schedule.")

    try:
        supabase.table("barber_schedules").delete().eq("barber_id", barber["id"]).execute()
        if not slots:
            return []
        payload = [
            {**slot.model_dump(mode="json"), "barber_id": barber["id"]} for slot in slots
        ]
        result = supabase.table("barber_schedules").insert(payload).execute()
        logger.info("Schedule updated for barber %s (%d active days)", barber["id"], len(slots))
        return result.data or []
    except Exception:
        logger.exception("Failed to save barber schedule")
        raise HTTPException(status_code=503, detail="Could not save the schedule right now.")


@router.get("/time-off")
def list_time_off(barber: dict = Depends(get_current_barber)):
    try:
        result = (
            supabase.table("barber_time_off")
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
def create_time_off(data: TimeOffCreate, barber: dict = Depends(get_current_barber)):
    try:
        payload = {**data.model_dump(mode="json"), "barber_id": barber["id"]}
        result = supabase.table("barber_time_off").insert(payload).execute()
        if not result.data:
            raise HTTPException(status_code=400, detail="Could not create time off.")
        return result.data[0]
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to create time off")
        raise HTTPException(status_code=503, detail="Could not create time off right now.")


@router.delete("/time-off/{time_off_id}", status_code=204)
def delete_time_off(time_off_id: str, barber: dict = Depends(get_current_barber)):
    try:
        existing = (
            supabase.table("barber_time_off")
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
        supabase.table("barber_time_off").delete().eq("id", time_off_id).execute()
    except Exception:
        logger.exception("Failed to delete time off")
        raise HTTPException(status_code=503, detail="Could not delete time off right now.")
