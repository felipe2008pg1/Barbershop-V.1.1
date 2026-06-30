"""
Field-level encryption for sensitive PII (phone, email).

Design:
- AES-256-GCM (authenticated encryption) for the stored value — random
  nonce per call, so two encryptions of the same plaintext never match.
  This is what protects the data at rest if the DB is ever exposed.
- HMAC-SHA256 "blind index" for fields that need equality lookups
  (client_phone). Deterministic by design — same input always produces
  the same hash — so it can be used in a `WHERE` clause / unique index,
  but it does NOT reveal the original value and cannot be reversed.

Key management:
- A single 32-byte key (DATA_ENCRYPTION_KEY, base64-encoded) is loaded
  from the environment. It must NEVER be stored in the database or in
  version control. Losing this key means the encrypted data is
  permanently unreadable — back it up securely (e.g., your secrets
  manager / Render's env var store), not in the repo.
- Key rotation is out of scope for this module; rotating requires
  decrypting all rows with the old key and re-encrypting with the new
  one in a maintenance script.
"""
import base64
import hashlib
import hmac
import os
import secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_SIZE = 12  # 96-bit nonce, standard for GCM


def _load_key() -> bytes:
    raw = os.getenv("DATA_ENCRYPTION_KEY")
    if not raw:
        raise RuntimeError(
            "DATA_ENCRYPTION_KEY is not set. Generate one with: "
            "python -c \"import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())\""
        )
    try:
        key = base64.b64decode(raw)
    except Exception:
        raise RuntimeError("DATA_ENCRYPTION_KEY is not valid base64.")
    if len(key) != 32:
        raise RuntimeError("DATA_ENCRYPTION_KEY must decode to exactly 32 bytes (AES-256).")
    return key


def _load_hmac_key() -> bytes:
    raw = os.getenv("DATA_BLIND_INDEX_KEY")
    if not raw:
        raise RuntimeError(
            "DATA_BLIND_INDEX_KEY is not set. Generate one with: "
            "python -c \"import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())\""
        )
    try:
        key = base64.b64decode(raw)
    except Exception:
        raise RuntimeError("DATA_BLIND_INDEX_KEY is not valid base64.")
    if len(key) != 32:
        raise RuntimeError("DATA_BLIND_INDEX_KEY must decode to exactly 32 bytes.")
    return key


_AESGCM = AESGCM(_load_key()) if os.getenv("DATA_ENCRYPTION_KEY") else None
_HMAC_KEY = _load_hmac_key() if os.getenv("DATA_BLIND_INDEX_KEY") else None


def encrypt_field(plaintext: str | None) -> str | None:
    """Encrypts a string for storage. Returns base64(nonce || ciphertext)."""
    if plaintext is None:
        return None
    aesgcm = _AESGCM or AESGCM(_load_key())
    nonce = secrets.token_bytes(_NONCE_SIZE)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_field(stored: str | None) -> str | None:
    """Decrypts a value produced by encrypt_field. Returns None on empty input."""
    if stored is None or stored == "":
        return None
    aesgcm = _AESGCM or AESGCM(_load_key())
    raw = base64.b64decode(stored)
    nonce, ciphertext = raw[:_NONCE_SIZE], raw[_NONCE_SIZE:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


def _normalize(value: str) -> str:
    """Normalizes input before hashing so lookups are consistent
    regardless of formatting (whitespace, case for emails)."""
    return value.strip().lower()


def blind_index(value: str | None) -> str | None:
    """
    Deterministic HMAC-SHA256 of the normalized value, for use as a
    lookup/uniqueness column. NOT reversible — cannot recover the
    original value from this hash.
    """
    if value is None or value == "":
        return None
    key = _HMAC_KEY or _load_hmac_key()
    digest = hmac.new(key, _normalize(value).encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")
