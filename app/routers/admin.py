"""
Admin routes: protected by a simple secret key (ADMIN_API_KEY).
Used only by you, the shop owner, to register barbers and manage
the list of services/prices, and to view revenue/performance reports.
"""
import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query, Request

from app.config import supabase
from app.auth import require_admin
from app.models import BarberCreate, BarberUpdate, ServiceCreate, ServiceUpdate
from app.rate_limit import limiter
from app.security.password_policy import validate_password
from app.security.crypto import encrypt_field, blind_index, decrypt_field

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])
logger = logging.getLogger("barbershop.admin")


def _decrypt_barber(row: dict) -> dict:
    out = dict(row)
    out["email"] = decrypt_field(row.get("email_enc"))
    out["phone"] = decrypt_field(row.get("phone_enc")) if row.get("phone_enc") else None
    out.pop("email_enc", None)
    out.pop("email_hash", None)
    out.pop("phone_enc", None)
    return out


# ---------- Barbers ----------

@router.get("/barbers")
def list_all_barbers():
    """Lists all barbers (active and inactive)."""
    try:
        result = supabase.table("barbers").select("*").order("name").execute()
        return [_decrypt_barber(row) for row in (result.data or [])]
    except Exception:
        logger.exception("Failed to list barbers")
        raise HTTPException(status_code=503, detail="Could not load barbers right now.")


@router.post("/barbers", status_code=201)
@limiter.limit("20/minute")
def create_barber(request: Request, data: BarberCreate):
    """
    Creates the barber's login in Supabase Auth and the matching
    profile in the `barbers` table.
    """
    # Defense in depth: BarberCreate already enforces the password policy
    # via its field_validator, but re-checking here guarantees this route
    # never creates a weak-password account even if the model changes.
    validate_password(data.password, data.email)

    email_hash = blind_index(data.email)
    try:
        existing = (
            supabase.table("barbers")
            .select("id")
            .eq("email_hash", email_hash)
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.exception("Failed to check for existing barber email")
        raise HTTPException(status_code=503, detail="Could not create the barber right now.")

    if existing and existing.data:
        raise HTTPException(status_code=409, detail="A barber with this email already exists.")

    try:
        auth_result = supabase.auth.admin.create_user(
            {
                "email": data.email,
                "password": data.password,
                "email_confirm": True,
            }
        )
    except Exception:
        logger.exception("Failed to create barber auth login")
        raise HTTPException(status_code=400, detail="Could not create the barber's login.")

    if not auth_result or not auth_result.user:
        raise HTTPException(status_code=400, detail="Could not create the barber's login.")

    barber_id = auth_result.user.id

    profile = {
        "id": barber_id,
        "name": data.name,
        "email_enc": encrypt_field(data.email),
        "email_hash": email_hash,
        "phone_enc": encrypt_field(data.phone) if data.phone else None,
    }

    try:
        result = supabase.table("barbers").insert(profile).execute()
        if not result.data:
            raise HTTPException(status_code=400, detail="Could not create the barber profile.")
        logger.info("Barber created: %s", data.name)
        return _decrypt_barber(result.data[0])
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to create barber profile after auth signup")
        try:
            supabase.auth.admin.delete_user(barber_id)
        except Exception:
            logger.exception("Failed to roll back orphaned auth user %s", barber_id)
        raise HTTPException(status_code=400, detail="Could not create the barber profile.")


@router.put("/barbers/{barber_id}")
def update_barber(barber_id: str, data: BarberUpdate):
    """Edits barber data or activates/deactivates their access."""
    raw_payload = {k: v for k, v in data.model_dump(mode="json").items() if v is not None}
    if not raw_payload:
        raise HTTPException(status_code=400, detail="No data to update.")

    payload = dict(raw_payload)
    if "phone" in payload:
        payload["phone_enc"] = encrypt_field(payload.pop("phone"))

    try:
        result = supabase.table("barbers").update(payload).eq("id", barber_id).execute()
    except Exception:
        logger.exception("Failed to update barber")
        raise HTTPException(status_code=503, detail="Could not update the barber right now.")

    if not result.data:
        raise HTTPException(status_code=404, detail="Barber not found.")
    logger.info("Barber %s updated: %s", barber_id, list(raw_payload.keys()))
    return _decrypt_barber(result.data[0])


@router.delete("/barbers/{barber_id}", status_code=204)
def delete_barber(barber_id: str):
    """
    Revokes the barber's access (soft-delete: marks as inactive instead of
    deleting, to preserve appointment history).
    """
    try:
        result = (
            supabase.table("barbers")
            .update({"active": False})
            .eq("id", barber_id)
            .execute()
        )
    except Exception:
        logger.exception("Failed to deactivate barber")
        raise HTTPException(status_code=503, detail="Could not deactivate the barber right now.")

    if not result.data:
        raise HTTPException(status_code=404, detail="Barber not found.")
    logger.info("Barber %s deactivated", barber_id)


# ---------- Services ----------

@router.get("/services")
def list_all_services():
    try:
        result = supabase.table("services").select("*").order("name").execute()
        return result.data or []
    except Exception:
        logger.exception("Failed to list services")
        raise HTTPException(status_code=503, detail="Could not load services right now.")


@router.post("/services", status_code=201)
def create_service(data: ServiceCreate):
    try:
        result = supabase.table("services").insert(data.model_dump(mode="json")).execute()
        if not result.data:
            raise HTTPException(status_code=400, detail="Could not create the service.")
        logger.info("Service created: %s", data.name)
        return result.data[0]
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to create service")
        raise HTTPException(status_code=503, detail="Could not create the service right now.")


@router.put("/services/{service_id}")
def update_service(service_id: str, data: ServiceUpdate):
    payload = {k: v for k, v in data.model_dump(mode="json").items() if v is not None}
    if not payload:
        raise HTTPException(status_code=400, detail="No data to update.")

    try:
        result = supabase.table("services").update(payload).eq("id", service_id).execute()
    except Exception:
        logger.exception("Failed to update service")
        raise HTTPException(status_code=503, detail="Could not update the service right now.")

    if not result.data:
        raise HTTPException(status_code=404, detail="Service not found.")
    logger.info("Service %s updated: %s", service_id, list(payload.keys()))
    return result.data[0]


@router.delete("/services/{service_id}", status_code=204)
def delete_service(service_id: str):
    """Soft-delete: marks the service as inactive instead of deleting it."""
    try:
        result = (
            supabase.table("services")
            .update({"active": False})
            .eq("id", service_id)
            .execute()
        )
    except Exception:
        logger.exception("Failed to deactivate service")
        raise HTTPException(status_code=503, detail="Could not deactivate the service right now.")

    if not result.data:
        raise HTTPException(status_code=404, detail="Service not found.")
    logger.info("Service %s deactivated", service_id)


# ---------- Dashboard / reports ----------

@router.get("/reports/dashboard")
def get_dashboard(
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
):
    """
    Returns a revenue and performance summary based on completed
    appointments only (status = 'completed'), optionally filtered by
    a date range.

    If no date range is given, defaults to the last 30 days.
    """
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before end_date.")

    try:
        result = (
            supabase.table("appointments")
            .select("date, barber_id, service_id, barbers(name), services(name, price)")
            .eq("status", "completed")
            .gte("date", str(start_date))
            .lte("date", str(end_date))
            .execute()
        )
    except Exception:
        logger.exception("Failed to load dashboard data")
        raise HTTPException(status_code=503, detail="Could not load the dashboard right now.")

    appointments = result.data or []

    total_revenue = 0.0
    total_completed = len(appointments)

    by_day: dict[str, dict] = defaultdict(lambda: {"revenue": 0.0, "count": 0})
    by_barber: dict[str, dict] = defaultdict(lambda: {"barber_name": "", "revenue": 0.0, "count": 0})
    by_service: dict[str, dict] = defaultdict(lambda: {"service_name": "", "revenue": 0.0, "count": 0})

    for appt in appointments:
        service_info = appt.get("services") or {}
        barber_info = appt.get("barbers") or {}
        price = float(service_info.get("price") or 0)

        total_revenue += price

        day_key = appt["date"]
        by_day[day_key]["revenue"] += price
        by_day[day_key]["count"] += 1

        barber_id = appt.get("barber_id") or "unknown"
        by_barber[barber_id]["barber_name"] = barber_info.get("name") or "Unknown"
        by_barber[barber_id]["revenue"] += price
        by_barber[barber_id]["count"] += 1

        service_id = appt.get("service_id") or "unknown"
        by_service[service_id]["service_name"] = service_info.get("name") or "Unknown"
        by_service[service_id]["revenue"] += price
        by_service[service_id]["count"] += 1

    revenue_by_day = [
        {"date": day, "revenue": round(data["revenue"], 2), "count": data["count"]}
        for day, data in sorted(by_day.items())
    ]

    revenue_by_barber = sorted(
        [
            {
                "barber_id": barber_id,
                "barber_name": data["barber_name"],
                "revenue": round(data["revenue"], 2),
                "count": data["count"],
            }
            for barber_id, data in by_barber.items()
        ],
        key=lambda x: x["revenue"],
        reverse=True,
    )

    revenue_by_service = sorted(
        [
            {
                "service_id": service_id,
                "service_name": data["service_name"],
                "revenue": round(data["revenue"], 2),
                "count": data["count"],
            }
            for service_id, data in by_service.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )

    return {
        "total_revenue": round(total_revenue, 2),
        "total_completed": total_completed,
        "period_start": str(start_date),
        "period_end": str(end_date),
        "revenue_by_day": revenue_by_day,
        "revenue_by_barber": revenue_by_barber,
        "revenue_by_service": revenue_by_service,
    }

# ---------- Appointments list (with filters) ----------

@router.get("/appointments")
def list_appointments(
    date: Optional[str] = Query(default=None),
    barber_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
):
    """Lists all appointments with optional filters."""
    if status and status not in {"scheduled", "completed", "cancelled"}:
        raise HTTPException(status_code=400, detail="Invalid status filter.")

    try:
        query = (
            supabase.table("appointments")
            .select("*, services(name, price, duration_minutes), barbers(name)")
            .order("date")
            .order("time")
        )
        if date:
            query = query.eq("date", date)
        if barber_id:
            query = query.eq("barber_id", barber_id)
        if status:
            query = query.eq("status", status)

        result = query.execute()
        rows = result.data or []
        for row in rows:
            row["client_phone"] = decrypt_field(row.get("client_phone_enc"))
            row["client_email"] = decrypt_field(row.get("client_email_enc")) if row.get("client_email_enc") else None
            row.pop("client_phone_enc", None)
            row.pop("client_phone_hash", None)
            row.pop("client_email_enc", None)
        return rows
    except Exception:
        logger.exception("Failed to list appointments")
        raise HTTPException(status_code=503, detail="Could not load appointments right now.")


# ---------- Today's summary ----------

@router.get("/reports/today")
def get_today_summary():
    """
    Returns a quick summary of today's appointments:
    total, completed, cancelled, no-shows (scheduled but in the past).
    """
    today = date.today().isoformat()

    try:
        result = (
            supabase.table("appointments")
            .select("id, status, time")
            .eq("date", today)
            .execute()
        )
    except Exception:
        logger.exception("Failed to load today summary")
        raise HTTPException(status_code=503, detail="Could not load today's summary right now.")

    appointments = result.data or []
    from datetime import datetime as dt
    now_time = dt.now().strftime("%H:%M:%S")

    total = len(appointments)
    completed = sum(1 for a in appointments if a["status"] == "completed")
    cancelled = sum(1 for a in appointments if a["status"] == "cancelled")
    no_show = sum(
        1 for a in appointments
        if a["status"] == "scheduled" and a["time"] < now_time
    )
    upcoming = sum(
        1 for a in appointments
        if a["status"] == "scheduled" and a["time"] >= now_time
    )

    return {
        "date": today,
        "total": total,
        "completed": completed,
        "cancelled": cancelled,
        "no_show": no_show,
        "upcoming": upcoming,
    }


# ---------- Client ranking ----------

@router.get("/reports/clients")
def get_client_ranking(
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
):
    """
    Returns top clients by visit count and total spend.
    Only counts completed appointments.
    """
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=90)

    try:
        result = (
            supabase.table("appointments")
            .select("client_name, client_phone_enc, client_phone_hash, services(price)")
            .eq("status", "completed")
            .gte("date", str(start_date))
            .lte("date", str(end_date))
            .execute()
        )
    except Exception:
        logger.exception("Failed to load client ranking")
        raise HTTPException(status_code=503, detail="Could not load client ranking right now.")

    from collections import defaultdict
    clients: dict[str, dict] = defaultdict(lambda: {"name": "", "visits": 0, "total_spent": 0.0})

    for appt in (result.data or []):
        phone_hash = appt["client_phone_hash"]
        phone = decrypt_field(appt.get("client_phone_enc"))
        price = float((appt.get("services") or {}).get("price") or 0)
        clients[phone_hash]["name"] = appt["client_name"]
        clients[phone_hash]["phone"] = phone
        clients[phone_hash]["visits"] += 1
        clients[phone_hash]["total_spent"] += price

    ranking = sorted(
        [
            {
                "client_phone": data["phone"],
                "client_name": data["name"],
                "visits": data["visits"],
                "total_spent": round(data["total_spent"], 2),
            }
            for data in clients.values()
        ],
        key=lambda x: (x["visits"], x["total_spent"]),
        reverse=True,
    )

    return ranking[:limit]


# ---------- Peak hours ----------

@router.get("/reports/peak-hours")
def get_peak_hours(
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
):
    """
    Returns appointment counts grouped by hour of day and weekday,
    counting only completed appointments.
    """
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=90)

    try:
        result = (
            supabase.table("appointments")
            .select("date, time")
            .eq("status", "completed")
            .gte("date", str(start_date))
            .lte("date", str(end_date))
            .execute()
        )
    except Exception:
        logger.exception("Failed to load peak hours")
        raise HTTPException(status_code=503, detail="Could not load peak hours right now.")

    from collections import defaultdict
    from datetime import datetime as dt

    by_hour: dict[int, int] = defaultdict(int)
    by_weekday: dict[int, int] = defaultdict(int)

    for appt in (result.data or []):
        hour = int(appt["time"][:2])
        by_hour[hour] += 1

        appt_date = dt.strptime(appt["date"], "%Y-%m-%d")
        weekday_db = (appt_date.weekday() + 1) % 7
        by_weekday[weekday_db] += 1

    return {
        "by_hour": [
            {"hour": h, "label": f"{h:02d}:00", "count": by_hour[h]}
            for h in sorted(by_hour)
        ],
        "by_weekday": [
            {"weekday": w, "count": by_weekday[w]}
            for w in sorted(by_weekday)
        ],
    }
