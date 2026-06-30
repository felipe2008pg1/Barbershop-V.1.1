"""
Login attempt guard — blocks IP and email after repeated failures.
Complements SlowAPI's rate limiting with credential-based lockout.

Limits:
- 5 failures per IP in 15 min → blocks IP for 15 min
- 10 failures per email in 30 min → blocks email for 30 min
  (protects against distributed attacks that rotate IPs)
"""

import time
from collections import defaultdict
from fastapi import HTTPException, status
import logging

logger = logging.getLogger("barbershop.security")


class LoginGuard:
    def __init__(
        self,
        ip_max_failures: int = 5,
        ip_window: int = 900,       # 15 min
        ip_lockout: int = 900,      # 15 min
        email_max_failures: int = 10,
        email_window: int = 1800,   # 30 min
        email_lockout: int = 1800,  # 30 min
    ):
        self._ip_max = ip_max_failures
        self._ip_window = ip_window
        self._ip_lockout = ip_lockout
        self._email_max = email_max_failures
        self._email_window = email_window
        self._email_lockout = email_lockout

        self._ip_failures: dict[str, list[float]] = defaultdict(list)
        self._email_failures: dict[str, list[float]] = defaultdict(list)
        self._ip_blocked_until: dict[str, float] = {}
        self._email_blocked_until: dict[str, float] = {}

    def check(self, ip: str, email: str) -> None:
        """Raises 429 if IP or email is locked out."""
        now = time.time()

        if ip in self._ip_blocked_until and now < self._ip_blocked_until[ip]:
            remaining = int(self._ip_blocked_until[ip] - now)
            logger.warning("login_blocked_ip ip=%s remaining=%ds", ip, remaining)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed attempts. Try again in {remaining // 60 + 1} minute(s).",
            )

        email_key = email.lower().strip()
        if email_key in self._email_blocked_until and now < self._email_blocked_until[email_key]:
            remaining = int(self._email_blocked_until[email_key] - now)
            logger.warning("login_blocked_email email=%s remaining=%ds", email_key, remaining)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed attempts. Try again in {remaining // 60 + 1} minute(s).",
            )

    def record_failure(self, ip: str, email: str) -> None:
        """Records a failed attempt and locks out if threshold reached."""
        now = time.time()
        email_key = email.lower().strip()

        # IP tracking
        self._ip_failures[ip] = [t for t in self._ip_failures[ip] if t > now - self._ip_window]
        self._ip_failures[ip].append(now)
        if len(self._ip_failures[ip]) >= self._ip_max:
            self._ip_blocked_until[ip] = now + self._ip_lockout
            logger.warning("login_ip_locked ip=%s failures=%d", ip, len(self._ip_failures[ip]))

        # Email tracking
        self._email_failures[email_key] = [
            t for t in self._email_failures[email_key] if t > now - self._email_window
        ]
        self._email_failures[email_key].append(now)
        if len(self._email_failures[email_key]) >= self._email_max:
            self._email_blocked_until[email_key] = now + self._email_lockout
            logger.warning("login_email_locked email=%s failures=%d", email_key, len(self._email_failures[email_key]))

    def record_success(self, ip: str, email: str) -> None:
        """Clears failure counters on successful login."""
        email_key = email.lower().strip()
        self._ip_failures.pop(ip, None)
        self._ip_blocked_until.pop(ip, None)
        self._email_failures.pop(email_key, None)
        self._email_blocked_until.pop(email_key, None)


# Singleton
login_guard = LoginGuard()
