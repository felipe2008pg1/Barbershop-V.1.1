"""
Pydantic models: validate the shape of data going in and out of the API.
"""
import re
from datetime import date, time, date as date_cls
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


def _validate_brazilian_phone(value: str) -> str:
    """
    Validates and normalizes a Brazilian phone number.
    Accepts formats like "(11) 99999-9999", "11999999999", "11 9999-9999".
    Stores only digits, requiring 10 or 11 digits (DDD + number).
    """
    digits = re.sub(r"\D", "", value or "")
    if len(digits) not in (10, 11):
        raise ValueError(
            "Phone number must include area code (DDD) and be 10 or 11 digits long."
        )
    return digits


def _validate_not_in_past(value: date_cls) -> date_cls:
    """Ensures a date is not earlier than today."""
    if value < date_cls.today():
        raise ValueError("Date cannot be in the past.")
    return value


# ---------- Services ----------

class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    duration_minutes: int = Field(gt=0, le=480, default=30)
    price: float = Field(ge=0, le=100000, default=0)


class ServiceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    duration_minutes: Optional[int] = Field(default=None, gt=0, le=480)
    price: Optional[float] = Field(default=None, ge=0, le=100000)
    active: Optional[bool] = None


# ---------- Barbers ----------

class BarberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: Optional[str] = None
    password: str = Field(min_length=6, max_length=72)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value):
        if value is None or value == "":
            return value
        return _validate_brazilian_phone(value)


class BarberUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    phone: Optional[str] = None
    photo_url: Optional[str] = None
    active: Optional[bool] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value):
        if value is None or value == "":
            return value
        return _validate_brazilian_phone(value)


class BarberLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


# ---------- Barber schedule (weekly working hours) ----------

class ScheduleSlot(BaseModel):
    weekday: int = Field(ge=0, le=6)  # 0 = Sunday ... 6 = Saturday
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


# ---------- Time off (one-off blocks) ----------

class TimeOffCreate(BaseModel):
    date: date
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    reason: Optional[str] = Field(default=None, max_length=200)

    @field_validator("date")
    @classmethod
    def date_not_in_past(cls, value):
        return _validate_not_in_past(value)

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, end_time, info):
        start_time = info.data.get("start_time")
        if start_time is not None and end_time is not None and end_time <= start_time:
            raise ValueError("end_time must be later than start_time.")
        return end_time


# ---------- Appointments ----------

class AppointmentCreate(BaseModel):
    barber_id: str
    service_id: str
    client_name: str = Field(min_length=1, max_length=120)
    client_phone: str
    client_email: Optional[EmailStr] = None
    date: date
    time: time
    notes: Optional[str] = Field(default=None, max_length=500)

    @field_validator("client_phone")
    @classmethod
    def validate_phone(cls, value):
        return _validate_brazilian_phone(value)

    @field_validator("date")
    @classmethod
    def date_not_in_past(cls, value):
        return _validate_not_in_past(value)


class AppointmentUpdate(BaseModel):
    service_id: Optional[str] = None
    client_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    client_phone: Optional[str] = None
    client_email: Optional[EmailStr] = None
    date: Optional[date] = None
    time: Optional[time] = None
    status: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=500)

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
    client_phone: str
    confirmation_code: str = Field(min_length=4, max_length=4)

    @field_validator("client_phone")
    @classmethod
    def validate_phone(cls, value):
        return _validate_brazilian_phone(value)

class DashboardQuery(BaseModel):
    """Optional date range filter for the admin dashboard report."""
    start_date: Optional[date] = None
    end_date: Optional[date] = None

class AppointmentReschedule(BaseModel):
    date: date
    time: time

    @field_validator("date")
    @classmethod
    def date_not_in_past(cls, value):
        return _validate_not_in_past(value)
