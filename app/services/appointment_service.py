"""
Appointment business logic — secure booking pipeline.

Status transition rules (enforced here AND in DB trigger):
  scheduled  → completed | cancelled
  pending    → scheduled | cancelled   (reserved, not used yet)
  completed  → nothing
  cancelled  → nothing

Extra rule: cannot mark as completed before the appointment datetime.
"""
import math
import logging
import random
import string
from datetime import datetime, timedelta, date as date_type
from typing import Optional
from app.services.barber_rate_guard import check_and_record_action
from fastapi import HTTPException
from app.config import supabase
from app.exceptions import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    SlotUnavailableError,
)
from app.services.audit_service import log_appointment_event

logger = logging.getLogger("barbershop.services.appointment")

_MAX_BOOKINGS_PER_IP_PER_DAY = 3

# Allowed transitions — single source of truth in Python
# (DB trigger is the safety net, this is the first line of defense)
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending":   {"scheduled", "cancelled"},
    "scheduled": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def _generate_confirmation_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choices(alphabet, k=4))


def generate_slots(start_time: str, end_time: str, slot_minutes: int) -> list[str]:
    fmt = "%H:%M:%S"
    start = datetime.strptime(start_time, fmt)
    end = datetime.strptime(end_time, fmt)
    slots, current = [], start
    while current < end:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=slot_minutes)
    return slots


# ------------------------------------------------------------------
# Transition validation
# ------------------------------------------------------------------

def validate_status_transition(
    current: str,
    requested: str,
    *,
    appointment_id: str = "unknown",
    actor_id: str = "unknown",
    actor_type: str = "barber",
    ip_address: str | None = None,
) -> None:
    """
    First line of defense.
    Logs invalid attempts to the audit log before raising.
    """
    allowed = _ALLOWED_TRANSITIONS.get(current, set())
    if requested == current:
        return

    if requested not in allowed:
        # Log the failed attempt
        log_appointment_event(
            appointment_id=appointment_id,
            actor_id=actor_id,
            actor_type=actor_type,
            action="invalid_transition_attempt",
            before_status=current,
            after_status=requested,
            before_data=None,
            after_data=None,
            ip_address=ip_address,
        )
        if not allowed:
            raise ConflictError(
                f"Appointments with status '{current}' cannot be changed."
            )
        raise ConflictError(
            f"Cannot change status from '{current}' to '{requested}'. "
            f"Allowed: {', '.join(sorted(allowed))}."
        )


def validate_completion_time(appt: dict) -> None:
    """
    Cannot mark as completed before the appointment's scheduled datetime.
    Mirrors the DB trigger so the error message is clear to the caller.
    """
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("America/Sao_Paulo")
    appt_dt_str = f"{appt['date']}T{appt['time']}"
    appt_dt = datetime.fromisoformat(appt_dt_str).replace(tzinfo=tz)
    now = datetime.now(tz=tz)
    if appt_dt > now:
        raise ConflictError(
            "Cannot mark this appointment as completed because it is still in the future."
        )


# ------------------------------------------------------------------
# Business rule checks
# ------------------------------------------------------------------

def _check_no_active_booking(client_phone: str) -> None:
    try:
        result = (
            supabase.table("appointments")
            .select("id")
            .eq("client_phone", client_phone)
            .eq("status", "scheduled")
            .limit(1)
            .execute()
        )
    except Exception:
        logger.exception("Failed to check active booking phone=***%s", client_phone[-4:])
        raise ServiceUnavailableError("Could not create the appointment right now.")

    if result.data:
        raise ConflictError(
            "You already have an active appointment. "
            "Please cancel it before booking a new one."
        )


def _check_ip_daily_limit(client_ip: str) -> None:
    today = date_type.today().isoformat()
    try:
        result = (
            supabase.table("appointments")
            .select("id", count="exact")
            .gte("created_at", f"{today}T00:00:00")
            .lte("created_at", f"{today}T23:59:59")
            .like("notes", f"[ip:{client_ip}]%")
            .execute()
        )
    except Exception:
        logger.exception("Failed to check IP daily limit ip=%s", client_ip)
        raise ServiceUnavailableError("Could not create the appointment right now.")

    count = result.count or 0
    if count >= _MAX_BOOKINGS_PER_IP_PER_DAY:
        logger.warning(
            "IP daily limit reached: ip=%s count=%d limit=%d",
            client_ip, count, _MAX_BOOKINGS_PER_IP_PER_DAY,
        )
        raise ConflictError(
            f"You have reached the maximum of {_MAX_BOOKINGS_PER_IP_PER_DAY} "
            "bookings per day from this connection. Try again tomorrow."
        )


def _check_slot_within_schedule(barber_id: str, appt_date: date_type, appt_time: str) -> None:
    # Before
    weekday_db = (appt_date.weekday() + 1) % 7

    # After
    from datetime import date as date_type_cls
    if isinstance(appt_date, str):
        appt_date = date_type_cls.fromisoformat(appt_date)
    weekday_db = (appt_date.weekday() + 1) % 7
    try:
        schedule = (
            supabase.table("barber_schedules")
            .select("start_time, end_time, slot_minutes")
            .eq("barber_id", barber_id)
            .eq("weekday", weekday_db)
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.exception("Failed to fetch schedule barber=%s", barber_id)
        raise ServiceUnavailableError("Could not create the appointment right now.")

    if not schedule or not schedule.data:
        raise ConflictError("The barber does not work on this day.")

    valid_slots = generate_slots(
        schedule.data["start_time"],
        schedule.data["end_time"],
        schedule.data["slot_minutes"],
    )
    if appt_time[:5] not in valid_slots:
        raise ConflictError("The requested time is outside the barber's working hours.")


# ------------------------------------------------------------------
# Public service functions
# ------------------------------------------------------------------

def get_availability(barber_id: str, date: date_type) -> dict:
    if date < date_type.today():
        return {"slots": [], "message": "This date is in the past."}

    weekday_db = (date.weekday() + 1) % 7

    try:
        schedule = (
            supabase.table("barber_schedules")
            .select("*")
            .eq("barber_id", barber_id)
            .eq("weekday", weekday_db)
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.exception("Failed to fetch schedule barber=%s date=%s", barber_id, date)
        raise ServiceUnavailableError("Could not check availability right now.")

    if not schedule or not schedule.data:
        return {"slots": [], "message": "Barber does not work on this day."}

    try:
        all_slots = generate_slots(
            schedule.data["start_time"],
            schedule.data["end_time"],
            schedule.data["slot_minutes"],
        )
        existing = (
            supabase.table("appointments")
            .select("time")
            .eq("barber_id", barber_id)
            .eq("date", str(date))
            .neq("status", "cancelled")
            .execute()
        )
        taken = {row["time"][:5] for row in (existing.data or [])}

        time_off = (
            supabase.table("barber_time_off")
            .select("*")
            .eq("barber_id", barber_id)
            .eq("date", str(date))
            .execute()
        )
        blocked = set()
        for block in (time_off.data or []):
            if block["start_time"] is None or block["end_time"] is None:
                return {"slots": [], "message": "Barber unavailable on this date."}
            blocked.update(
                generate_slots(
                    block["start_time"],
                    block["end_time"],
                    schedule.data["slot_minutes"],
                )
            )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to compute availability barber=%s date=%s", barber_id, date)
        raise ServiceUnavailableError("Could not check availability right now.")

    return {"slots": [s for s in all_slots if s not in taken and s not in blocked]}


def create_appointment(payload: dict, client_ip: str) -> dict:
    from datetime import date as _date_cls

    client_phone = payload["client_phone"]
    raw_date = payload["date"]
    appt_date = _date_cls.fromisoformat(raw_date) if isinstance(raw_date, str) else raw_date
    appt_time: str = str(payload["time"])

    _check_slot_within_schedule(payload["barber_id"], appt_date, appt_time)
    _check_no_active_booking(client_phone)
    _check_ip_daily_limit(client_ip)

    try:
        barber = (
            supabase.table("barbers")
            .select("id")
            .eq("id", payload["barber_id"])
            .eq("active", True)
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.exception("Failed to verify barber=%s", payload["barber_id"])
        raise ServiceUnavailableError("Could not create the appointment right now.")

    if not barber or not barber.data:
        raise NotFoundError("Selected barber")

    try:
        service = (
            supabase.table("services")
            .select("id")
            .eq("id", payload["service_id"])
            .eq("active", True)
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.exception("Failed to verify service=%s", payload["service_id"])
        raise ServiceUnavailableError("Could not create the appointment right now.")

    if not service or not service.data:
        raise NotFoundError("Selected service")

    user_notes = payload.get("notes") or ""
    notes_with_ip = f"[ip:{client_ip}] {user_notes}".strip()

    last_error = None
    for attempt in range(5):
        code = _generate_confirmation_code()
        try:
            result = supabase.rpc(
                "create_appointment_atomic",
                {
                    "p_barber_id": payload["barber_id"],
                    "p_service_id": payload["service_id"],
                    "p_client_name": payload["client_name"],
                    "p_client_phone": client_phone,
                    "p_client_email": payload.get("client_email"),
                    "p_date": str(appt_date),
                    "p_time": appt_time,
                    "p_notes": notes_with_ip,
                    "p_confirmation_code": code,
                },
            ).execute()

            if not result.data:
                raise ServiceUnavailableError("Could not create the appointment right now.")

            row = result.data[0]

            log_appointment_event(
                appointment_id=row["id"],
                actor_id=client_phone,
                actor_type="customer",
                action="created",
                before_status=None,
                after_status=row.get("status"),
                before_data=None,
                after_data=row,
                ip_address=client_ip,
            )

            logger.info(
                "Appointment created: id=%s barber=%s date=%s time=%s phone=***%s ip=%s attempt=%d",
                row.get("id"), payload["barber_id"], appt_date, appt_time,
                client_phone[-4:], client_ip, attempt + 1,
            )

            if row.get("notes", "").startswith(f"[ip:{client_ip}]"):
                row["notes"] = user_notes or None

            return row

        except HTTPException:
            raise
        except Exception as exc:
            last_error = exc
            err = str(exc).lower()
            if "slot_taken" in err or "duplicate key" in err or "unique" in err:
                logger.warning(
                    "Slot conflict: barber=%s date=%s time=%s ip=%s",
                    payload["barber_id"], appt_date, appt_time, client_ip,
                )
                raise SlotUnavailableError()
            if "confirmation_code" in err:
                logger.warning("Confirmation code collision attempt=%d", attempt + 1)
                continue
            logger.exception(
                "Unexpected error creating appointment: barber=%s date=%s time=%s",
                payload["barber_id"], appt_date, appt_time,
            )
            raise ServiceUnavailableError("Could not create the appointment right now.")

    logger.error("Exhausted confirmation code retries: %s", last_error)
    raise ServiceUnavailableError("Could not create the appointment right now.")


def update_appointment_status(
    appointment_id: str,
    new_status: str,
    barber: dict,
) -> dict:
    """
    Full validated status-change pipeline:
      1. Rate guard (short window + daily limit)
      2. Fetch current state + ownership check
      3. Transition validation (Python + DB trigger)
      4. Completion time rule
      5. DB update
      6. Audit log
    """
    barber_id = barber["id"]

    # ── 1. Rate guard ────────────────────────────────────────────────
    check_and_record_action(barber_id)

    # ── 2. Fetch appointment ─────────────────────────────────────────
    try:
        existing = (
            supabase.table("appointments")
            .select("*")
            .eq("id", appointment_id)
            .eq("barber_id", barber_id)
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.exception("Failed to fetch appointment=%s", appointment_id)
        raise ServiceUnavailableError("Could not update the appointment right now.")

    if not existing or not existing.data:
        raise NotFoundError("Appointment")

    appt = existing.data
    current_status = appt["status"]

    # ── 3. Transition validation (logs invalid attempts) ─────────────
    validate_status_transition(
        current_status,
        new_status,
        appointment_id=appointment_id,
        actor_id=barber_id,
        actor_type="barber",
    )

    # ── 4. Completion time rule ──────────────────────────────────────
    if new_status == "completed":
        validate_completion_time(appt)

    # ── 5. DB update (trigger is the safety net) ─────────────────────
    try:
        result = (
            supabase.table("appointments")
            .update({"status": new_status})
            .eq("id", appointment_id)
            .execute()
        )
        if not result.data:
            raise ServiceUnavailableError("Could not update the appointment right now.")

        updated = result.data[0]

        # ── 6. Audit log ─────────────────────────────────────────────
        log_appointment_event(
            appointment_id=appointment_id,
            actor_id=barber_id,
            actor_type="barber",
            action="status_change",
            before_status=current_status,
            after_status=new_status,
            before_data=appt,
            after_data=updated,
        )

        logger.info(
            "Status changed: id=%s %s → %s barber=%s",
            appointment_id, current_status, new_status, barber_id,
        )
        return updated

    except HTTPException:
        raise
    except Exception as exc:
        err = str(exc).lower()
        if "invalid_transition" in err:
            raise ConflictError(
                f"Cannot change status from '{current_status}' to '{new_status}'."
            )
        if "completion_too_early" in err:
            raise ConflictError(
                "Cannot mark this appointment as completed because it is still in the future."
            )
        logger.exception("Failed to update status appointment=%s", appointment_id)
        raise ServiceUnavailableError("Could not update the appointment right now.")


def lookup_appointment(client_phone: str, confirmation_code: str, lang: str) -> dict:
    from app.service_translations import translate_service_name

    try:
        result = (
            supabase.table("appointments")
            .select("*, services(name, price, duration_minutes), barbers(name)")
            .eq("client_phone", client_phone)
            .eq("confirmation_code", confirmation_code.strip().upper())
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.exception("Lookup failed phone=***%s", client_phone[-4:])
        raise ServiceUnavailableError("Could not look up the appointment right now.")

    if not result or not result.data:
        raise NotFoundError("Appointment")

    appt = result.data
    notes = appt.get("notes") or ""
    if notes.startswith("[ip:"):
        appt["notes"] = notes.split("] ", 1)[1] if "] " in notes else None

    if appt.get("services"):
        appt["services"]["name"] = translate_service_name(appt["services"]["name"], lang)

    return appt


def cancel_appointment(
    appointment_id: str, client_phone: str, confirmation_code: str, lang: str,
    client_ip: Optional[str] = None,
) -> dict:
    from app.service_translations import translate_service_name

    try:
        existing = (
            supabase.table("appointments")
            .select("*")
            .eq("id", appointment_id)
            .eq("client_phone", client_phone)
            .eq("confirmation_code", confirmation_code.strip().upper())
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.exception("Failed to verify appointment=%s for cancellation", appointment_id)
        raise ServiceUnavailableError("Could not cancel the appointment right now.")

    if not existing or not existing.data:
        raise NotFoundError("Appointment")

    appt = existing.data
    current_status = appt["status"]

    # Validate transition (scheduled → cancelled only)
    validate_status_transition(current_status, "cancelled")

    try:
        supabase.table("appointments").update({"status": "cancelled"}).eq("id", appointment_id).execute()

        log_appointment_event(
            appointment_id=appointment_id,
            actor_id=client_phone,
            actor_type="customer",
            action="cancelled",
            before_status=current_status,
            after_status="cancelled",
            before_data=appt,
            after_data={**appt, "status": "cancelled"},
            ip_address=client_ip,
        )

        logger.info(
            "Appointment cancelled: id=%s phone=***%s",
            appointment_id, client_phone[-4:],
        )

        full = (
            supabase.table("appointments")
            .select("*, services(name, price, duration_minutes), barbers(name)")
            .eq("id", appointment_id)
            .maybe_single()
            .execute()
        )
        row = full.data if full and full.data else {**appt, "status": "cancelled"}

        notes = row.get("notes") or ""
        if notes.startswith("[ip:"):
            row["notes"] = notes.split("] ", 1)[1] if "] " in notes else None

        if row.get("services"):
            row["services"]["name"] = translate_service_name(row["services"]["name"], lang)

        return row

    except HTTPException:
        raise
    except Exception as exc:
        err = str(exc).lower()
        if "invalid_transition" in err:
            raise ConflictError(f"Cannot cancel an appointment with status '{current_status}'.")
        logger.exception("Failed to cancel appointment=%s", appointment_id)
        raise ServiceUnavailableError("Could not cancel the appointment right now.")
    
# Maximum number of reschedules allowed per appointment
_MAX_RESCHEDULES = 3

def reschedule_appointment(
    appointment_id: str,
    new_date: date_type,
    new_time_str: str,
    *,
    actor_id: str,
    actor_type: str,   # 'customer' | 'barber'
    client_phone: str | None = None,
    confirmation_code: str | None = None,
    barber_dict: dict | None = None,
    client_ip: str | None = None,
) -> dict:
    """
    Reschedules an existing appointment (Option B: update in place).

    Customer path  : requires client_phone + confirmation_code
    Barber path    : requires barber_dict (from token)

    Rules enforced:
      - Appointment must be 'scheduled' (not completed or cancelled)
      - New slot must be within barber's working hours
      - New slot must not conflict with existing booking
      - Max _MAX_RESCHEDULES reschedules per appointment
      - Cannot reschedule to same date+time (no-op guard)
      - Full audit log of before/after
    """

    # ── 1. Fetch and verify ownership ───────────────────────────────
    try:
        if actor_type == "customer":
            existing = (
                supabase.table("appointments")
                .select("*")
                .eq("id", appointment_id)
                .eq("client_phone", client_phone)
                .eq("confirmation_code", confirmation_code.strip().upper())
                .maybe_single()
                .execute()
            )
        else:  # barber
            existing = (
                supabase.table("appointments")
                .select("*")
                .eq("id", appointment_id)
                .eq("barber_id", barber_dict["id"])
                .maybe_single()
                .execute()
            )
    except Exception:
        logger.exception("Failed to fetch appointment=%s for reschedule", appointment_id)
        raise ServiceUnavailableError("Could not reschedule the appointment right now.")

    if not existing or not existing.data:
        raise NotFoundError("Appointment")

    appt = existing.data

    # ── 2. Status must be 'scheduled' ───────────────────────────────
    if appt["status"] != "scheduled":
        raise ConflictError(
            f"Only scheduled appointments can be rescheduled. "
            f"Current status: '{appt['status']}'."
        )

    # ── 3. Anti-abuse: max reschedules ──────────────────────────────
    reschedule_count = appt.get("reschedule_count") or 0
    if reschedule_count >= _MAX_RESCHEDULES:
        raise ConflictError(
            f"This appointment has already been rescheduled "
            f"{reschedule_count} time(s). "
            f"Maximum allowed is {_MAX_RESCHEDULES}. "
            "Please cancel and create a new booking."
        )

    # ── 4. No-op guard ──────────────────────────────────────────────
    current_date = str(appt["date"])
    current_time = str(appt["time"])[:5]
    if str(new_date) == current_date and new_time_str[:5] == current_time:
        raise ConflictError("The new date and time are the same as the current booking.")

    # ── 5. Validate new slot within barber's schedule ───────────────
    _check_slot_within_schedule(appt["barber_id"], new_date, new_time_str)

    # ── 6. Check new slot is not already taken ──────────────────────
    try:
        conflict = (
            supabase.table("appointments")
            .select("id")
            .eq("barber_id", appt["barber_id"])
            .eq("date", str(new_date))
            .eq("time", new_time_str)
            .neq("status", "cancelled")
            .neq("id", appointment_id)   # exclude self
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.exception("Failed to check slot conflict for reschedule appointment=%s", appointment_id)
        raise ServiceUnavailableError("Could not reschedule the appointment right now.")

    if conflict and conflict.data:
        raise SlotUnavailableError()

    # ── 7. Update in place ──────────────────────────────────────────
    try:
        result = (
            supabase.table("appointments")
            .update({
                "date": str(new_date),
                "time": new_time_str,
                "reschedule_count": reschedule_count + 1,
            })
            .eq("id", appointment_id)
            .execute()
        )
        if not result.data:
            raise ServiceUnavailableError("Could not reschedule the appointment right now.")

        updated = result.data[0]

        # ── 8. Audit log ─────────────────────────────────────────────
        log_appointment_event(
            appointment_id=appointment_id,
            actor_id=actor_id,
            actor_type=actor_type,
            action="rescheduled",
            before_status=appt["status"],
            after_status=updated["status"],
            before_data=appt,
            after_data=updated,
            ip_address=client_ip,
        )

        logger.info(
            "Appointment rescheduled: id=%s %s %s → %s %s actor=%s reschedule_count=%d",
            appointment_id,
            current_date, current_time,
            new_date, new_time_str,
            actor_id,
            reschedule_count + 1,
        )

        return updated

    except HTTPException:
        raise
    except Exception as exc:
        err = str(exc).lower()
        if "duplicate key" in err or "unique" in err:
            raise SlotUnavailableError()
        logger.exception("Failed to update appointment=%s for reschedule", appointment_id)
        raise ServiceUnavailableError("Could not reschedule the appointment right now.")
