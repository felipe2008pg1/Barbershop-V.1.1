"""
Security middleware: WAF, rate limiting, IP blocking, security headers.
"""

import re
import time
import ipaddress
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

import logging
logger = logging.getLogger("barbershop.security")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class RateLimitConfig:
    requests_per_minute: int = 60
    requests_per_hour: int = 600
    auth_requests_per_minute: int = 10
    auth_requests_per_hour: int = 30
    block_threshold: int = 5
    block_duration_seconds: int = 900  # 15 min


@dataclass
class WAFConfig:
    max_body_size_bytes: int = 1 * 1024 * 1024  # 1 MB
    max_url_length: int = 2048
    max_header_count: int = 50
    max_query_params: int = 30

    sqli_patterns: list = field(default_factory=lambda: [
        r"(?i)(\bunion\b.+\bselect\b)",
        r"(?i)(\bselect\b.+\bfrom\b)",
        r"(?i)(\bdrop\b.+\btable\b)",
        r"(?i)(\binsert\b.+\binto\b)",
        r"(?i)(\bdelete\b.+\bfrom\b)",
        r"(?i)(\bupdate\b.+\bset\b)",
        r"(?i)(--\s*$|;\s*--)",
        r"(?i)(\bexec\b|\bexecute\b)\s*\(",
        r"(?i)\bxp_cmdshell\b",
        r"'[^']*'[^']*'",
    ])

    xss_patterns: list = field(default_factory=lambda: [
        r"(?i)<\s*script[^>]*>",
        r"(?i)javascript\s*:",
        r"(?i)on\w+\s*=",
        r"(?i)<\s*iframe[^>]*>",
        r"(?i)<\s*object[^>]*>",
        r"(?i)<\s*embed[^>]*>",
        r"(?i)data\s*:\s*text\s*/\s*html",
        r"(?i)vbscript\s*:",
    ])

    path_traversal_patterns: list = field(default_factory=lambda: [
        r"\.\./",
        r"\.\.\\",
        r"%2e%2e%2f",
        r"%2e%2e/",
        r"\.\.%2f",
        r"%252e%252e",
    ])

    blocked_ua_fragments: list = field(default_factory=lambda: [
        "sqlmap", "nikto", "nmap", "masscan", "zgrab", "nuclei",
        "dirbuster", "gobuster", "wfuzz", "hydra", "metasploit",
        "burpsuite", "havij", "acunetix", "nessus", "openvas",
    ])


# ---------------------------------------------------------------------------
# In-memory IP store (single-instance; replace with Redis for multi-instance)
# ---------------------------------------------------------------------------

class IPStore:
    def __init__(self):
        self._minute_counts: dict[str, list[float]] = defaultdict(list)
        self._hour_counts: dict[str, list[float]] = defaultdict(list)
        self._violations: dict[str, int] = defaultdict(int)
        self._blocked_until: dict[str, float] = {}

    def is_blocked(self, ip: str) -> bool:
        until = self._blocked_until.get(ip)
        if until and time.time() < until:
            return True
        if ip in self._blocked_until:
            del self._blocked_until[ip]
        return False

    def block(self, ip: str, duration: int) -> None:
        self._blocked_until[ip] = time.time() + duration
        logger.warning("ip_blocked ip=%s duration=%ds", ip, duration)

    def record_violation(self, ip: str, threshold: int, block_duration: int) -> None:
        self._violations[ip] += 1
        if self._violations[ip] >= threshold:
            self.block(ip, block_duration)
            self._violations[ip] = 0

    def check_rate(self, ip: str, rpm: int, rph: int) -> tuple[bool, str]:
        now = time.time()
        self._minute_counts[ip] = [t for t in self._minute_counts[ip] if t > now - 60]
        self._hour_counts[ip] = [t for t in self._hour_counts[ip] if t > now - 3600]

        if len(self._minute_counts[ip]) >= rpm:
            return False, "minute"
        if len(self._hour_counts[ip]) >= rph:
            return False, "hour"

        self._minute_counts[ip].append(now)
        self._hour_counts[ip].append(now)
        return True, ""

    def cleanup(self) -> None:
        now = time.time()
        for ip in list(self._minute_counts):
            self._minute_counts[ip] = [t for t in self._minute_counts[ip] if t > now - 60]
            if not self._minute_counts[ip]:
                del self._minute_counts[ip]
        for ip in list(self._hour_counts):
            self._hour_counts[ip] = [t for t in self._hour_counts[ip] if t > now - 3600]
            if not self._hour_counts[ip]:
                del self._hour_counts[ip]


_ip_store = IPStore()
_rl_cfg = RateLimitConfig()
_waf_cfg = WAFConfig()

_SQLI_RE = [re.compile(p) for p in _waf_cfg.sqli_patterns]
_XSS_RE = [re.compile(p) for p in _waf_cfg.xss_patterns]
_PATH_RE = [re.compile(p) for p in _waf_cfg.path_traversal_patterns]
_BLOCKED_UA = [f.lower() for f in _waf_cfg.blocked_ua_fragments]

_AUTH_PREFIXES = ("/auth", "/login", "/token", "/admin/login", "/barber/login")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_real_ip(request: Request) -> str:
    for header in ("CF-Connecting-IP", "X-Real-IP"):
        ip = request.headers.get(header)
        if ip:
            return ip.strip().split(",")[0].strip()
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.strip().split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_private_ip(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False


def _waf_scan(text: str) -> tuple[bool, str]:
    for p in _SQLI_RE:
        if p.search(text):
            return False, "sqli"
    for p in _XSS_RE:
        if p.search(text):
            return False, "xss"
    for p in _PATH_RE:
        if p.search(text):
            return False, "path_traversal"
    return True, ""


def _security_headers() -> dict[str, str]:
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": (
            "geolocation=(), microphone=(), camera=(), payment=(), usb=(), "
            "magnetometer=(), gyroscope=(), accelerometer=(), midi=(), "
            "interest-cohort=(), browsing-topics=()"
        ),
        "Content-Security-Policy": (
            "default-src 'self'; "
            # No inline <script> tags exist anywhere in the templates — every
            # script is loaded from /static/js via <script src>. 'unsafe-inline'
            # here is required only because the UI uses onclick="..." attribute
            # handlers extensively (both static in the templates and generated
            # dynamically by admin.js/barber.js/public.js). Removing it would
            # break every button in the app. Migrating to addEventListener +
            # nonces is the long-term fix, not a "quick win".
            "script-src 'self' 'unsafe-inline'; "
            # Same reasoning for style="..." attributes, used throughout the
            # templates and the JS-rendered HTML fragments.
            "style-src 'self' 'unsafe-inline'; "
            # Nothing in the app currently loads images from arbitrary https
            # hosts (barber photo_url exists in the schema but isn't rendered
            # anywhere yet) — scoped to self + data: URIs only. If external
            # barber photos are added later, this needs an explicit host.
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "upgrade-insecure-requests;"
        ),
        "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Cache-Control": "no-store",
    }


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self._cleanup_counter = 0

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        ip = _get_real_ip(request)

        self._cleanup_counter += 1
        if self._cleanup_counter >= 500:
            _ip_store.cleanup()
            self._cleanup_counter = 0

        if not _is_private_ip(ip):
            result = await self._run_checks(request, ip)
            if result is not None:
                return result

        response = await call_next(request)
        self._inject_headers(response)
        return response

    async def _run_checks(self, request: Request, ip: str) -> Response | None:
        # 1. IP blocked?
        if _ip_store.is_blocked(ip):
            logger.warning("blocked_ip ip=%s path=%s", ip, request.url.path)
            return self._deny(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests. Try again later.")

        # 2. User-Agent
        ua = request.headers.get("user-agent", "").lower()
        if not ua or any(f in ua for f in _BLOCKED_UA):
            logger.warning("blocked_ua ip=%s ua=%.120s", ip, ua)
            _ip_store.record_violation(ip, _rl_cfg.block_threshold, _rl_cfg.block_duration_seconds)
            return self._deny(status.HTTP_403_FORBIDDEN, "Forbidden.")

        # 3. Sanity checks
        if len(str(request.url)) > _waf_cfg.max_url_length:
            return self._deny(status.HTTP_414_REQUEST_URI_TOO_LONG, "URI too long.")
        if len(request.headers) > _waf_cfg.max_header_count:
            return self._deny(status.HTTP_431_REQUEST_HEADER_FIELDS_TOO_LARGE, "Too many headers.")
        if len(request.query_params) > _waf_cfg.max_query_params:
            return self._deny(status.HTTP_400_BAD_REQUEST, "Too many query parameters.")

        # 4. Rate limiting
        is_auth = request.url.path.startswith(_AUTH_PREFIXES)
        rpm = _rl_cfg.auth_requests_per_minute if is_auth else _rl_cfg.requests_per_minute
        rph = _rl_cfg.auth_requests_per_hour if is_auth else _rl_cfg.requests_per_hour

        allowed, window = _ip_store.check_rate(ip, rpm, rph)
        if not allowed:
            logger.warning("rate_limited ip=%s path=%s window=%s", ip, request.url.path, window)
            _ip_store.record_violation(ip, _rl_cfg.block_threshold, _rl_cfg.block_duration_seconds)
            return self._deny(status.HTTP_429_TOO_MANY_REQUESTS, f"Rate limit exceeded ({window} window).")

        # 5. WAF — URL
        clean, threat = _waf_scan(str(request.url))
        if not clean:
            logger.warning("waf_block_url ip=%s threat=%s", ip, threat)
            _ip_store.record_violation(ip, _rl_cfg.block_threshold, _rl_cfg.block_duration_seconds)
            return self._deny(status.HTTP_400_BAD_REQUEST, "Malformed request.")

        # 6. WAF — Body
        content_type = request.headers.get("content-type", "")
        if (
            request.method in ("POST", "PUT", "PATCH")
            and any(ct in content_type for ct in ("json", "form", "text"))
        ):
            body = await request.body()
            if len(body) > _waf_cfg.max_body_size_bytes:
                return self._deny(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Request body too large.")
            try:
                clean, threat = _waf_scan(body.decode("utf-8", errors="replace"))
                if not clean:
                    logger.warning("waf_block_body ip=%s threat=%s", ip, threat)
                    _ip_store.record_violation(ip, _rl_cfg.block_threshold, _rl_cfg.block_duration_seconds)
                    return self._deny(status.HTTP_400_BAD_REQUEST, "Malformed request.")
            except Exception:
                pass

        return None

    @staticmethod
    def _deny(status_code: int, message: str) -> JSONResponse:
        r = JSONResponse(status_code=status_code, content={"detail": message})
        for k, v in _security_headers().items():
            r.headers[k] = v
        return r

    @staticmethod
    def _inject_headers(response: Response) -> None:
        for k, v in _security_headers().items():
            if k not in response.headers:
                response.headers[k] = v
