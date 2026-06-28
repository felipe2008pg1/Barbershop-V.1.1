"""
Audit log service — append-only record of every appointment event.
Never raises: audit failure must never block the main flow.
"""
import logging
from typing import Optional

from app.config import supabase

logger = logging.getLogger("barbershop.audit")


def log_appointment_event(
    *,
    appointment_id: str,
    actor_id: str,
    actor_type: str,           # 'barber' | 'customer' | 'admin'
    action: str,               # 'created' | 'status_change' | 'cancelled' | 'invalid_transition_attempt'
    before_status: Optional[str] = None,
    after_status: Optional[str] = None,
    before_data: Optional[dict] = None,
    after_data: Optional[dict] = None,
    ip_address: Optional[str] = None,
    success: bool = True,
) -> None:
    """
    Writes one immutable audit record.
    Swallows all exceptions — audit failure must never block the operation.
    `success=False` marks rejected/invalid attempts.
    """
    try:
        supabase.table("appointment_audit_log").insert(
            {
                "appointment_id": appointment_id,
                "actor_id": actor_id,
                "actor_type": actor_type,
                "action": action,
                "before_status": before_status,
                "after_status": after_status,
                "before_data": before_data,
                "after_data": after_data,
                "ip_address": ip_address,
                "success": success,
            }
        ).execute()
    except Exception:
        logger.exception(
            "Failed to write audit log: appointment=%s actor=%s action=%s success=%s",
            appointment_id, actor_id, action, success,
        )
