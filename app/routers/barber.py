"""
Barber area routes (requires login via Supabase Auth).
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from app.service_translations import translate_service_name
from app.config import supabase
from app.auth import get_current_barber
from app.models import AppointmentUpdate, ScheduleSlot, TimeOffCreate, BarberLogin
from app.rate_limit import limiter

router = APIRouter(prefix="/api/barber", tags=["barber"])
logger = logging.getLogger("barbershop.barber")


@router.post("/login")
@limiter.limit("10/minute")
def login(request: Request, credentials: BarberLogin):
    """
    Logs the barber in using email/password against Supabase Auth.
    Returns the access_token (JWT) to be used in subsequent requests.

    Rate limited to slow down credential brute-forcing attempts.
    """
    try:
        result = supabase.auth.sign_in_with_password(
            {"email": credentials.email, "password": credentials.password}
        )
    except Exception:
        logger.info("Failed login attempt for %s from %s", credentials.email, request.client.host)
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if not result or not result.session:
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

    logger.info("Barber %s logged in", credentials.email)
    return {
        "access_token": result.session.access_token,
        "barber": profile.data,
    }


@router.get("/me")
def get_me(barber: dict = Depends(get_current_barber)):
    """Returns the authenticated barber's profile."""
    return barber


@router.get("/appointments")
def list_my_appointments(
    request: Request,
    date: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    barber: dict = Depends(get_current_barber),
):
    """
    Lists the logged-in barber's appointments, including full
    customer details (name, phone, email). Service names are
    translated based on the X-Lang request header.
    """
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
    """
    Updates an appointment.
    If 'status' is in the payload, routes through the validated
    transition pipeline. Other fields (notes, time, etc.) are updated
    directly after confirming ownership.
    """
    from app.services.appointment_service import update_appointment_status

    payload = {k: v for k, v in data.model_dump(mode="json").items() if v is not None}
    if not payload:
        raise HTTPException(status_code=400, detail="No data to update.")

    # Status change → full validation pipeline
    if "status" in payload:
        if len(payload) > 1:
            raise HTTPException(
                status_code=400,
                detail="Status must be updated alone, not mixed with other fields.",
            )
        return update_appointment_status(appointment_id, payload["status"], barber)

    # Non-status update (notes, time, etc.) — verify ownership first
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


# ---------- Weekly schedule (each barber sets their own) ----------

@router.get("/schedule")
def get_schedule(barber: dict = Depends(get_current_barber)):
    """Returns the schedule configured by the logged-in barber."""
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
    """
    Replaces the logged-in barber's weekly schedule with the provided list.
    Send one item per weekday they work.
    """
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


# ---------- Time off / blocked periods ----------

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
