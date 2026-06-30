"""
Entry point: FastAPI app, middleware, routers, global error handlers.
"""
import logging
import os
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi.errors import RateLimitExceeded
from app.config import CORS_ALLOWED_ORIGINS, DEBUG_LOGGING, ENVIRONMENT
from app.logging_config import configure_logging
from app.rate_limit import limiter
from app.routers import admin, barber, public
from app.middleware import (
    SecurityMiddleware,
    HTTPSEnforcementMiddleware,
    CloudflareOriginMiddleware,
    RequestIDMiddleware,
    register_cors,
)

configure_logging(debug=DEBUG_LOGGING)
logger = logging.getLogger("barbershop.main")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
is_production = ENVIRONMENT == "production"

app = FastAPI(
    title="BarberShop",
    docs_url=None,
    redoc_url=None,
)

app.state.limiter = limiter

# ------------------------------------------------------------------
# Global error handlers
# ------------------------------------------------------------------

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning("Rate limit: ip=%s path=%s", request.client.host, request.url.path)
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please wait a moment and try again."},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    clean = [
        {"field": " → ".join(str(loc) for loc in e["loc"]), "message": e["msg"]}
        for e in errors
    ]
    logger.info("Validation error on %s: %s", request.url.path, clean)
    return JSONResponse(status_code=422, content={"detail": clean})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again later."},
    )


# ------------------------------------------------------------------
# Middleware (ordem importa — último adicionado = mais externo)
# ------------------------------------------------------------------

if CORS_ALLOWED_ORIGINS == ["*"] and is_production:
    logger.warning("CORS is open to all origins (*). Restrict before deploying to production.")

register_cors(app)                                                    # 1. innermost
app.add_middleware(SecurityMiddleware)                                # 2. WAF + rate limit + IP block
app.add_middleware(CloudflareOriginMiddleware)                        # 3. bloqueia acesso direto ao Render
app.add_middleware(HTTPSEnforcementMiddleware, enforce=is_production) # 4. valida X-Forwarded-Proto
app.add_middleware(RequestIDMiddleware)                               # 5. outermost


@app.middleware("http")
async def request_logging(request: Request, call_next):
    response = await call_next(request)
    logger.info(
        "%s %s %s ip=%s",
        request.method,
        request.url.path,
        response.status_code,
        request.client.host if request.client else "unknown",
    )
    return response


# ------------------------------------------------------------------
# Static files, templates, routers
# ------------------------------------------------------------------

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

app.include_router(public.router)
app.include_router(barber.router)
app.include_router(admin.router)


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/barber-area", response_class=HTMLResponse)
async def barber_area(request: Request):
    return templates.TemplateResponse(request, "barber.html")


@app.get("/admin", response_class=HTMLResponse)
async def admin_area(request: Request):
    return templates.TemplateResponse(request, "admin.html")


@app.on_event("startup")
async def on_startup():
    logger.info("BarberShop starting. CORS origins: %s", CORS_ALLOWED_ORIGINS)


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("BarberShop shutting down.")
