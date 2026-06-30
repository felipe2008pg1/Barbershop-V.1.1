"""
Public routes: no login required.
"""
import logging
from datetime import date as date_type
from fastapi import APIRouter, Query, Request
from app.models import AppointmentCreate, AppointmentLookup, AppointmentReschedule
from app.models import AppointmentCreate, AppointmentLookup
from app.rate_limit import limiter
from app.services.appointment_service import (
    cancel_appointment,
    create_appointment,
    get_availability,
    lookup_appointment,
)
router = APIRouter(prefix="/api/public", tags=["public"])
logger = logging.getLogger("barbershop.public")
def _lang(request: Request) -> str:
    lang = (request.headers.get("X-Lang") or "pt").strip().lower()
    return lang if lang in ("pt", "en") else "pt"


@router.get("/services")
def list_services(request: Request):
    # Uses the anon-key client: this is unauthenticated, public data,
    # and the public_read_active_services RLS policy is the actual
    # enforcement here (not just the .eq("active", True) filter).
    from app.config import get_anon_client
    from app.service_translations import translate_service_name
    lang = _lang(request)
    try:
        result = (
            get_anon_client()
            .table("services")
            .select("id, name, duration_minutes, price")
            .eq("active", True)
            .order("name")
            .execute()
        )
        services = result.data or []
        for s in services:
            s["name"] = translate_service_name(s["name"], lang)
        return services
    except Exception:
        logger.exception("Failed to list services")
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Could not load services right now.")


@router.get("/barbers")
def list_barbers():
    from app.config import get_anon_client
    from fastapi import HTTPException
    try:
        result = (
            get_anon_client()
            .table("barbers")
            .select("id, name, photo_url")
            .eq("active", True)
            .order("name")
            .execute()
        )
        return result.data or []
    except Exception:
        logger.exception("Failed to list barbers")
        raise HTTPException(status_code=503, detail="Could not load barbers right now.")


@router.get("/availability")
def get_availability_route(
    barber_id: str = Query(...),
    date: date_type = Query(...),
):
    return get_availability(barber_id, date)


@router.post("/appointments", status_code=201)
@limiter.limit("5/minute")
def create_appointment_route(request: Request, appointment: AppointmentCreate):
    # Booking creation, lookup, cancel, and reschedule below stay on the
    # service-role client (inside appointment_service.py) by design: the
    # customer is never an authenticated Supabase principal (no login),
    # so there's no auth.uid() for RLS to scope against. Least privilege
    # for this flow is enforced at the application layer instead — strict
    # Pydantic validation, the phone+confirmation_code ownership check on
    # every read, and the public_insert_appointments policy's WITH CHECK
    # (status/active-barber/active-service/date checks) as a second line
    # of defense in case this code path is ever bypassed.
    client_ip = request.client.host if request.client else "unknown"
    return create_appointment(appointment.model_dump(mode="json"), client_ip)


@router.post("/appointments/lookup")
@limiter.limit("10/minute")
def lookup_appointment_route(request: Request, lookup: AppointmentLookup):
    return lookup_appointment(lookup.client_phone, lookup.confirmation_code, _lang(request))


@router.post("/appointments/{appointment_id}/cancel")
@limiter.limit("10/minute")
def cancel_appointment_route(request: Request, appointment_id: str, lookup: AppointmentLookup):
    client_ip = request.client.host if request.client else "unknown"
    return cancel_appointment(
        appointment_id,
        lookup.client_phone,
        lookup.confirmation_code,
        _lang(request),
        client_ip,
    )


@router.put("/appointments/{appointment_id}/reschedule")
@limiter.limit("5/minute")
def reschedule_appointment_route(
    request: Request,
    appointment_id: str,
    new_schedule: "AppointmentReschedule",
    lookup: AppointmentLookup,
):
    from app.models import AppointmentReschedule
    from app.services.appointment_service import reschedule_appointment
    client_ip = request.client.host if request.client else "unknown"
    return reschedule_appointment(
        appointment_id,
        new_schedule.date,
        str(new_schedule.time),
        actor_id=lookup.client_phone,
        actor_type="customer",
        client_phone=lookup.client_phone,
        confirmation_code=lookup.confirmation_code,
        client_ip=client_ip,
    )
