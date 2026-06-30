"""
HTTPS enforcement and CORS hardening.
"""

import os
from typing import Callable

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

import logging
logger = logging.getLogger("barbershop.security")

_EXEMPT_PATHS = {"/health", "/ping"}


class HTTPSEnforcementMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, enforce: bool = True):
        super().__init__(app)
        self._enforce = enforce

    async def dispatch(self, request: Request, call_next: Callable):
        if self._enforce and request.url.path not in _EXEMPT_PATHS:
            proto = request.headers.get("X-Forwarded-Proto", "https")
            if proto != "https":
                logger.warning("http_rejected path=%s", request.url.path)
                return JSONResponse(
                    status_code=status.HTTP_301_MOVED_PERMANENTLY,
                    content={"detail": "HTTPS required."},
                    headers={"Location": str(request.url).replace("http://", "https://", 1)},
                )
        return await call_next(request)


def register_cors(app) -> None:
    # Reads the same env var already used by config.py
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "*")
    origins = [o.strip() for o in raw.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Admin-Key", "X-Lang", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )
