"""
Strong password policy.

Rules:
- Minimum of 12 characters
- At least 1 uppercase letter
- At least 1 lowercase letter
- At least 1 number
- At least 1 special character
- Cannot contain the user's email
- Cannot be a common, well-known password
"""

import re
from fastapi import HTTPException, status

# Top most used passwords — expand as needed
_COMMON_PASSWORDS = {
    "password", "password1", "12345678", "123456789", "1234567890",
    "qwerty123", "iloveyou", "admin123", "letmein1", "welcome1",
    "monkey123", "dragon123", "master123", "abc123456", "pass1234",
    "senha123", "senha1234", "mudar123", "trocar123",
}

_MIN_LENGTH = 12
_UPPER_RE = re.compile(r"[A-Z]")
_LOWER_RE = re.compile(r"[a-z]")
_DIGIT_RE = re.compile(r"\d")
_SPECIAL_RE = re.compile(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~]")


def validate_password(password: str, email: str = "") -> None:
    """
    Validates password against policy.
    Raises HTTPException 400 with a descriptive message on failure.
    """
    errors = []

    if len(password) < _MIN_LENGTH:
        errors.append(f"at least {_MIN_LENGTH} characters")
    if not _UPPER_RE.search(password):
        errors.append("at least one uppercase letter")
    if not _LOWER_RE.search(password):
        errors.append("at least one lowercase letter")
    if not _DIGIT_RE.search(password):
        errors.append("at least one number")
    if not _SPECIAL_RE.search(password):
        errors.append("at least one special character (!@#$%^&* etc.)")
    if password.lower() in _COMMON_PASSWORDS:
        errors.append("must not be a commonly used password")
    if email and email.split("@")[0].lower() in password.lower():
        errors.append("must not contain your email address")

    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password does not meet requirements: {'; '.join(errors)}.",
        )
