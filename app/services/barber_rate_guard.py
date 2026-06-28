"""
Rate guard for barber status-change actions.

Rules:
  - Short window : more than 10 actions in 5 minutes  → block for 5 minutes
  - Daily limit  : more than 50 actions in a day      → block until midnight
  - On block     : return exact (rounded) minutes remaining

All state lives in the DB so it survives server restarts and works
correctly if you ever run multiple workers.
"""
import logging
import math
from datetime import datetime, date as date_type, timezone, timedelta

from fastapi import HTTPException

from app.config import supabase

logger = logging.getLogger("barbershop.barber_rate_guard")

_SHORT_WINDOW_MINUTES = 5
_SHORT_WINDOW_LIMIT = 10
_BLOCK_DURATION_MINUTES = 5
_DAILY_LIMIT = 50


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _minutes_remaining(until: datetime) -> int:
    """Returns ceiling of minutes left, minimum 1."""
    now = _now_utc()
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    delta = (until - now).total_seconds()
    return max(1, math.ceil(delta / 60))


def _raise_blocked(blocked_until: datetime, reason: str) -> None:
    minutes = _minutes_remaining(blocked_until)
    raise HTTPException(
        status_code=429,
        detail=(
            f"Too many status changes. "
            f"Please wait {minutes} minute{'s' if minutes != 1 else ''} before trying again."
        ),
    )


def check_and_record_action(barber_id: str) -> None:
    """
    Call this before every status change by a barber.
    Raises 429 if the barber is blocked or has exceeded a limit.
    Records the action if allowed.
    """
    now = _now_utc()
    today = date_type.today()

    # ── 1. Check existing block ──────────────────────────────────────
    try:
        block = (
            supabase.table("barber_action_blocks")
            .select("blocked_until, reason")
            .eq("barber_id", barber_id)
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.exception("Failed to check action block for barber=%s", barber_id)
        raise HTTPException(status_code=503, detail="Could not process the request right now.")

    if block and block.data:
        raw = block.data["blocked_until"]
        # Supabase returns ISO string
        if isinstance(raw, str):
            blocked_until = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            blocked_until = raw
        if blocked_until > now:
            _raise_blocked(blocked_until, block.data.get("reason", ""))
        else:
            # Block expired — clean up
            try:
                supabase.table("barber_action_blocks").delete().eq("barber_id", barber_id).execute()
            except Exception:
                logger.warning("Failed to clear expired block for barber=%s", barber_id)

    # ── 2. Load or initialise counters ───────────────────────────────
    try:
        row = (
            supabase.table("barber_action_counts")
            .select("*")
            .eq("barber_id", barber_id)
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.exception("Failed to load action counts for barber=%s", barber_id)
        raise HTTPException(status_code=503, detail="Could not process the request right now.")

    if not row or not row.data:
        # First action ever — create row
        try:
            supabase.table("barber_action_counts").insert({
                "barber_id": barber_id,
                "window_start": now.isoformat(),
                "window_count": 1,
                "day_date": today.isoformat(),
                "day_count": 1,
                "updated_at": now.isoformat(),
            }).execute()
        except Exception:
            logger.exception("Failed to create action count for barber=%s", barber_id)
        return  # first action always allowed

    data = row.data

    # ── 3. Reset short window if expired ────────────────────────────
    raw_window_start = data["window_start"]
    if isinstance(raw_window_start, str):
        window_start = datetime.fromisoformat(raw_window_start.replace("Z", "+00:00"))
    else:
        window_start = raw_window_start

    window_expired = (now - window_start).total_seconds() > _SHORT_WINDOW_MINUTES * 60
    if window_expired:
        window_count = 0
        window_start = now
    else:
        window_count = data["window_count"]

    # ── 4. Reset daily counter if new day ───────────────────────────
    raw_day = data["day_date"]
    if isinstance(raw_day, str):
        stored_day = date_type.fromisoformat(raw_day)
    else:
        stored_day = raw_day

    if stored_day != today:
        day_count = 0
    else:
        day_count = data["day_count"]

    # ── 5. Check limits BEFORE recording ────────────────────────────
    new_window_count = window_count + 1
    new_day_count = day_count + 1

    block_reason = None
    block_until = None

    if new_window_count > _SHORT_WINDOW_LIMIT:
        block_reason = f"Exceeded {_SHORT_WINDOW_LIMIT} actions in {_SHORT_WINDOW_MINUTES} minutes"
        block_until = now + timedelta(minutes=_BLOCK_DURATION_MINUTES)

    elif new_day_count > _DAILY_LIMIT:
        # Block until midnight UTC
        tomorrow = (today + timedelta(days=1))
        block_until = datetime(
            tomorrow.year, tomorrow.month, tomorrow.day,
            0, 0, 0, tzinfo=timezone.utc
        )
        block_reason = f"Exceeded {_DAILY_LIMIT} actions today"

    if block_reason:
        # Record block
        try:
            supabase.table("barber_action_blocks").upsert({
                "barber_id": barber_id,
                "blocked_until": block_until.isoformat(),
                "reason": block_reason,
                "created_at": now.isoformat(),
            }).execute()
        except Exception:
            logger.exception("Failed to write block for barber=%s", barber_id)

        logger.warning(
            "Barber blocked: id=%s reason=%s until=%s",
            barber_id, block_reason, block_until.isoformat(),
        )
        _raise_blocked(block_until, block_reason)

    # ── 6. Record the action ─────────────────────────────────────────
    try:
        supabase.table("barber_action_counts").upsert({
            "barber_id": barber_id,
            "window_start": window_start.isoformat(),
            "window_count": new_window_count,
            "day_date": today.isoformat(),
            "day_count": new_day_count,
            "updated_at": now.isoformat(),
        }).execute()
    except Exception:
        logger.exception("Failed to update action count for barber=%s", barber_id)
        # Non-fatal: allow the action, log the failure
