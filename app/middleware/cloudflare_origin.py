"""
Bloqueia requisições que chegam diretamente ao Render, bypassando o Cloudflare.

Setup:
1. Gere um secret: python -c "import secrets; print(secrets.token_hex(32))"
2. Adicione no Render: CLOUDFLARE_ORIGIN_SECRET=<secret>
3. Cloudflare → Rules → Transform Rules → Modify Request Header:
   Header: X-Origin-Secret | Value: <mesmo secret>
4. Render → ENFORCE_CLOUDFLARE_ORIGIN=true
"""

import hmac
import os
from typing import Callable

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

import logging
logger = logging.getLogger("barbershop.security")

_SECRET = os.getenv("CLOUDFLARE_ORIGIN_SECRET", "")
_ENFORCE = os.getenv("ENFORCE_CLOUDFLARE_ORIGIN", "false").lower() == "true"
_EXEMPT = {"/health", "/ping"}


class CloudflareOriginMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        if _ENFORCE and not _SECRET:
            raise RuntimeError(
                "ENFORCE_CLOUDFLARE_ORIGIN=true mas CLOUDFLARE_ORIGIN_SECRET não está definido."
            )

    async def dispatch(self, request: Request, call_next: Callable):
        if not _ENFORCE or request.url.path in _EXEMPT:
            return await call_next(request)

        incoming = request.headers.get("X-Origin-Secret", "")
        if not _SECRET or not hmac.compare_digest(incoming, _SECRET):
            logger.warning(
                "direct_origin_blocked path=%s ip=%s",
                request.url.path,
                request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Forbidden."},
            )

        return await call_next(request)
