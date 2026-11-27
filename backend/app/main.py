"""FastAPI application factory."""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.errors import DomainError
from app.core.logging import configure_logging, request_id_var
from app.db.session import get_engine

log = logging.getLogger("modelguard.api")

API_PREFIX = "/api/v1"

TAGS = [
    {"name": "auth", "description": "Sign in and the caller's permissions"},
    {"name": "inventory", "description": "Module A: enterprise model inventory"},
    {"name": "monitoring", "description": "Module B: performance monitoring, drift and threshold breaches"},
    {"name": "validations", "description": "Module C: validation workflow and evidence"},
    {"name": "findings", "description": "Module C: findings and remediation"},
    {"name": "ai-governance", "description": "Module D: AI systems, EU AI Act readiness, LLM evaluation, bias testing"},
    {"name": "regulatory", "description": "Module F: regulatory sources, requirements and control mapping"},
    {"name": "reporting", "description": "Module E: executive dashboard, committee packs and PDF reports"},
    {"name": "audit", "description": "Module F: append-only audit trail"},
    {"name": "system", "description": "Health and reference data"},
]


def _error(status: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "details": details,
                                                              "request_id": request_id_var.get()}})


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="ModelGuard API",
        version="1.0.0",
        description=("Financial crime model risk management and AI governance platform. All data is synthetic. "
                     "Simulated assessments do not constitute regulatory certification."),
        openapi_tags=TAGS,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        if len(rid) > 64:
            rid = str(uuid.uuid4())
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
        if not request.url.path.startswith(("/docs", "/redoc")):
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        log.info("request", extra={"method": request.method, "path": request.url.path,
                                   "status": response.status_code,
                                   "duration_ms": round((time.perf_counter() - start) * 1000, 1)})
        return response

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError):
        return _error(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return _error(422, "validation_error", "Request validation failed", details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        code = {401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}.get(
            exc.status_code, "http_error")
        resp = _error(exc.status_code, code, str(exc.detail))
        if exc.headers:
            resp.headers.update(exc.headers)
        return resp

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return _error(500, "internal_error", "An unexpected error occurred")

    @app.get(f"{API_PREFIX}/health", tags=["system"])
    def health():
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": get_engine().dialect.name, "environment": settings.env,
                "as_of": get_settings().today().isoformat(), "institution": settings.institution_name}

    from app.api.routes import register

    register(app, API_PREFIX)
    return app


app = create_app()
