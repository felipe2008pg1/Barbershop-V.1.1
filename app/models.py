"""
Pydantic models: validate the shape of data going in and out of the API.

Security posture:
- All input models use extra='forbid' — unexpected fields are rejected
  with 422, not silently ignored. Prevents mass assignment attacks.
- All text fields are stripped of leading/trailing whitespace and
  Unicode control characters before storage.
- UUIDs from clients (barber_id, service_id) are validated to be
  well-formed before hitting the DB.
"""
import re
import unicodedata
import uuid as _uuid_mod
from datetime import date, time, date as date_cls
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.security.password_policy import validate_password

# ---------- Helpers ----------

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize_text(value: str) -> str:
    """Strips leading/trailing whitespace and removes ASCII control characters
    (except tab and newline which are legitimate in notes). Normalizes to NFC."""
    if not value:
        return value
    value = _CONTROL_CHAR_RE.sub("", value)
    return unicodedata.normalize("NFC", value).strip()


def _validate_brazilian_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) not in (10, 11):
        raise ValueError(
            "Phone number must include area code (DDD) and be 10 or 11 digits long."
        )
    return digits


def _validate_not_in_past(value: date_cls) -> date_cls:
    if value < date_cls.today():
        raise ValueError("Date cannot be in the past.")
    return value


def _validate_uuid(value: str) -> str:
    try:
        _uuid_mod.UUID(value)
    except (ValueError, AttributeError):
        raise ValueError("Invalid UUID format.")
    return value


# ---------- Services ----------

class ServiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    duration_minutes: int = Field(gt=0, le=480, default=30)
    price: float = Field(ge=0, le=100_000, default=0)

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v): return _sanitize_text(v)


class ServiceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    duration_minutes: Optional[int] = Field(default=None, gt=0, le=480)
    price: Optional[float] = Field(default=None, ge=0, le=100_000)
    active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v):
        return _sanitize_text(v) if v else v


# ---------- Barbers ----------

class BarberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: Optional[str] = None
    password: str = Field(min_length=12, max_length=72)

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v): return _sanitize_text(v)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value):
        if value is None or value == "":
            return value
        return _validate_brazilian_phone(value)

    @field_validator("password")
    @classmethod
    def validate_password_policy(cls, value, info):
        email = info.data.get("email", "")
        try:
            validate_password(value, str(email) if email else "")
        except Exception as exc:
            raise ValueError(getattr(exc, "detail", str(exc)))
        return value


class BarberUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    phone: Optional[str] = None
    photo_url: Optional[str] = Field(default=None, max_length=2048)
    active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v):
        return _sanitize_text(v) if v else v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value):
        if value is None or value == "":
            return value
        return _validate_brazilian_phone(value)

    @field_validator("photo_url")
    @classmethod
    def validate_photo_url(cls, v):
        if v is None:
            return v
        if not v.startswith(("https://", "http://")):
            raise ValueError("photo_url must be a valid HTTP/HTTPS URL.")
        return v


class BarberLogin(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    """Replaces the raw `body: dict` in change_password endpoint."""
    model_config = ConfigDict(extra="forbid")

    new_password: str = Field(min_length=12, max_length=72)


# ---------- MFA ----------

class MFAEnrollVerify(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    factor_id: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class MFALoginVerify(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    factor_id: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class MFAUnenroll(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    factor_id: str = Field(min_length=1, max_length=128)


# ---------- Barber schedule ----------

class ScheduleSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    slot_minutes: int = Field(gt=0, le=240, default=30)

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, end_time, info):
        start_time = info.data.get("start_time")
        if start_time is not None and end_time <= start_time:
            raise ValueError("end_time must be later than start_time.")
        return end_time


# ---------- Time off ----------

class TimeOffCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    reason: Optional[str] = Field(default=None, max_length=200)

    @field_validator("date")
    @classmethod
    def date_not_in_past(cls, value):
        return _validate_not_in_past(value)

    @field_validator("reason")
    @classmethod
    def sanitize_reason(cls, v):
        return _sanitize_text(v) if v else v

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, end_time, info):
        start_time = info.data.get("start_time")
        if start_time is not None and end_time is not None and end_time <= start_time:
            raise ValueError("end_time must be later than start_time.")
        return end_time


# ---------- Appointments ----------

class AppointmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    barber_id: str
    service_id: str
    client_name: str = Field(min_length=1, max_length=120)
    client_phone: str
    client_email: Optional[EmailStr] = None
    date: date
    time: time
    notes: Optional[str] = Field(default=None, max_length=500)

    @field_validator("barber_id", "service_id")
    @classmethod
    def validate_uuid(cls, v): return _validate_uuid(v)

    @field_validator("client_name")
    @classmethod
    def sanitize_name(cls, v): return _sanitize_text(v)

    @field_validator("notes")
    @classmethod
    def sanitize_notes(cls, v):
        return _sanitize_text(v) if v else v

    @field_validator("client_phone")
    @classmethod
    def validate_phone(cls, value):
        return _validate_brazilian_phone(value)

    @field_validator("date")
    @classmethod
    def date_not_in_past(cls, value):
        return _validate_not_in_past(value)


class AppointmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    service_id: Optional[str] = None
    client_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    client_phone: Optional[str] = None
    client_email: Optional[EmailStr] = None
    date: Optional[date] = None
    time: Optional[time] = None
    status: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=500)

    @field_validator("service_id")
    @classmethod
    def validate_uuid(cls, v):
        return _validate_uuid(v) if v else v

    @field_validator("client_name")
    @classmethod
    def sanitize_name(cls, v):
        return _sanitize_text(v) if v else v

    @field_validator("notes")
    @classmethod
    def sanitize_notes(cls, v):
        return _sanitize_text(v) if v else v

    @field_validator("client_phone")
    @classmethod
    def validate_phone(cls, value):
        if value is None:
            return value
        return _validate_brazilian_phone(value)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value):
        if value is None:
            return value
        allowed = {"scheduled", "completed", "cancelled"}
        if value not in allowed:
            raise ValueError(f"Status must be one of: {', '.join(sorted(allowed))}.")
        return value


class AppointmentLookup(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    client_phone: str
    confirmation_code: str = Field(
        min_length=4, max_length=4, pattern=r"^[A-Z0-9]{4}$"
    )

    @field_validator("client_phone")
    @classmethod
    def validate_phone(cls, value):
        return _validate_brazilian_phone(value)

    @field_validator("confirmation_code")
    @classmethod
    def normalize_code(cls, v):
        return v.strip().upper()


class AppointmentReschedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    time: time

    @field_validator("date")
    @classmethod
    def date_not_in_past(cls, value):
        return _validate_not_in_past(value)


class DashboardQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: Optional[date] = None
    end_date: Optional[date] = None
