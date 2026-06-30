"""
One-time backfill: encrypts existing plaintext PII after Phase 1
migration has been applied. Run manually:

    python -m scripts.backfill_encryption

Requires DATA_ENCRYPTION_KEY and DATA_BLIND_INDEX_KEY to be set in
the environment (same values the app will use afterwards).

Idempotent: only processes rows where the encrypted column is still
NULL, so it's safe to re-run if it fails partway through.
"""
import logging
import sys

from app.config import supabase
from app.security.crypto import encrypt_field, blind_index

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill")


def backfill_appointments() -> None:
    result = (
        supabase.table("appointments")
        .select("id, client_phone, client_email")
        .is_("client_phone_enc", "null")
        .execute()
    )
    rows = result.data or []
    logger.info("Backfilling %d appointment rows...", len(rows))

    for row in rows:
        phone = row.get("client_phone")
        email = row.get("client_email")
        if not phone:
            logger.warning("Appointment %s has no client_phone — skipping.", row["id"])
            continue
        update = {
            "client_phone_enc": encrypt_field(phone),
            "client_phone_hash": blind_index(phone),
            "client_email_enc": encrypt_field(email) if email else None,
        }
        try:
            supabase.table("appointments").update(update).eq("id", row["id"]).execute()
        except Exception:
            logger.exception("Failed to backfill appointment %s", row["id"])
            raise

    logger.info("Appointments backfill complete.")


def backfill_barbers() -> None:
    result = (
        supabase.table("barbers")
        .select("id, email, phone")
        .is_("email_enc", "null")
        .execute()
    )
    rows = result.data or []
    logger.info("Backfilling %d barber rows...", len(rows))

    for row in rows:
        email = row.get("email")
        phone = row.get("phone")
        if not email:
            logger.warning("Barber %s has no email — skipping.", row["id"])
            continue
        update = {
            "email_enc": encrypt_field(email),
            "email_hash": blind_index(email),
            "phone_enc": encrypt_field(phone) if phone else None,
        }
        try:
            supabase.table("barbers").update(update).eq("id", row["id"]).execute()
        except Exception:
            logger.exception("Failed to backfill barber %s", row["id"])
            raise

    logger.info("Barbers backfill complete.")


if __name__ == "__main__":
    try:
        backfill_appointments()
        backfill_barbers()
    except Exception:
        logger.exception("Backfill aborted due to an error. Safe to re-run after fixing the cause.")
        sys.exit(1)
    logger.info("Backfill finished successfully. Verify with the queries in migration_v3_phase2, then run Phase 2.")
