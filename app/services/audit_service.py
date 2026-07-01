"""
Audit log service — append-only record of security-relevant events.

Never raises: audit failure must never block the main flow.

Two entry points:
- log_appointment_event(): existing API, unchanged for compatibility.
- log_security_event():    new — covers auth, admin actions, and any
                           event not tied to a specific appointment.
"""
import logging
from typing import Any, Optional

from app.config import supabase

logger = logging.getLogger("barbershop.audit")


def log_appointment_event(
    *,
    appointment_id: str,
    actor_id: str,
    actor_type: str,
    action: str,
    before_status: Optional[str] = None,
    after_status: Optional[str] = None,
    before_data: Optional[dict] = None,
    after_data: Optional[dict] = None,
    ip_address: Optional[str] = None,
    success: bool = True,
) -> None:
    """
    Writes one immutable audit record for an appointment event.
    Swallows all exceptions — audit failure must never block the operation.
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


def log_security_event(
    *,
    event: str,
    actor_id: str,
    actor_type: str,          # 'barber' | 'admin' | 'system'
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    target_id: Optional[str] = None,   # e.g. barber_id being deleted
    target_type: Optional[str] = None, # e.g. 'barber' | 'service'
    before_data: Optional[dict] = None,
    after_data: Optional[dict] = None,
    success: bool = True,
    detail: Optional[str] = None,
) -> None:
    """
    Writes a structured security/audit event for non-appointment actions:
    auth events, admin actions, permission changes, data mutations.

    Events use dot-notation namespacing:
      auth.login.success     auth.login.failure     auth.logout
      auth.mfa.enrolled      auth.mfa.unenrolled    auth.mfa.failure
      auth.password.changed
      admin.barber.created   admin.barber.updated   admin.barber.deactivated
      admin.service.created  admin.service.updated  admin.service.deactivated
      admin.permission.changed
    """
    try:
        supabase.table("security_audit_log").insert(
            {
                "event": event,
                "actor_id": actor_id,
                "actor_type": actor_type,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "target_id": target_id,
                "target_type": target_type,
                "before_data": before_data,
                "after_data": after_data,
                "success": success,
                "detail": detail,
            }
        ).execute()
    except Exception:
        logger.exception(
            "Failed to write security audit log: event=%s actor=%s target=%s success=%s",
            event, actor_id, target_id, success,
        )

    # Always mirror to the structured logger as well — gives you
    # grep-able logs even if the DB write fails.
    log_level = logging.INFO if success else logging.WARNING
    logger.log(
        log_level,
        "security_event event=%s actor=%s actor_type=%s target=%s success=%s ip=%s ua=%.80s detail=%s",
        event, actor_id, actor_type, target_id, success,
        ip_address, (user_agent or "")[:80], detail,
    )
