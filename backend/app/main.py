from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import alerts, analytics, auth, events, health, logs, metrics, otlp, projects, traces
from app.core.config import get_settings
from app.core.logging import safe_log_text, setup_logging
from app.db.session import dispose_engine, init_engine
from app.services.identity import IdentityService
from app.services.redis_client import close_redis, init_redis

logger = logging.getLogger(__name__)

OPENAPI_DESCRIPTION = """
ObservePro accepts telemetry from any language.

## Authentication

Ingestion uses a project API key:

    Authorization: Bearer op_...

The project is taken from that key. A `project_id` field in the body is ignored.

Dashboard and admin calls use a JWT from `POST /api/v1/auth/login`. Project-scoped
reads also send `X-Project-Id`. API keys may read telemetry only for their own project.

Creating projects and API keys requires an administrator JWT. The raw API key is
returned once and only its SHA-256 hash is stored.

A development collector token (`COLLECTOR_INGEST_TOKEN`) can ingest into the
bootstrap project. It is disabled in production when left as the published placeholder.

## Pagination and time

List endpoints accept `page` (default 1) and `page_size` (default 50, max 200).
Time filters accept `from` and `to` as ISO-8601 timestamps, or `range` of
`15m`, `1h`, `6h`, `24h`, or `7d`.

## Severity

Log severity is `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, or `FATAL`. Values are
normalized to OpenTelemetry severity numbers 1, 5, 9, 13, 17, and 21.

Alert severity is `INFO`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`, or `EMERGENCY`.
Mapped OpenTelemetry severities are INFO/9, INFO/10, WARN/13, ERROR/17, FATAL/21,
and FATAL/24.

## Idempotency and delivery

Send `Idempotency-Key` on log ingestion. The same key and payload returns the
original response for 24 hours. The same key with a different payload returns 409.
Delivery is at-least-once: a retry without an idempotency key can duplicate a log.
Span identity `(project, trace_id, span_id)` is upserted.

## Limits

Requests larger than `MAX_BODY_BYTES` are rejected with 413. Ingestion is rate
limited per API key. When Redis is unavailable the process keeps serving and
uses an in-process limiter; `/ready` reports Redis as degraded.

## OTLP

`POST /v1/traces`, `POST /v1/metrics`, and `POST /v1/logs` accept OTLP/HTTP JSON
and protobuf. OTLP/gRPC is served on `OTLP_GRPC_PORT` when enabled. The included
collector is the preferred scalable path and forwards OTLP to this API.

## Privacy

Telemetry may contain personal or confidential data. Apply access control and
the configured retention period. Common secret-like attribute names are redacted
before storage. Do not send secrets in log messages.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    for name in settings.insecure_defaults():
        logger.warning("%s is a development default. Change it before any shared deployment.", name)
    init_engine(settings.database_url)
    init_redis(settings.redis_url)
    from app.db.session import session_scope

    with session_scope() as db:
        identity = IdentityService(db)
        identity.seed_admin(settings)
        identity.bootstrap_dev_project(settings)
    grpc_server = None
    if settings.otlp_grpc_enabled:
        try:
            from app.telemetry.grpc_server import start_grpc_server

            grpc_server = start_grpc_server(settings.otlp_grpc_port)
        except Exception:
            logger.exception("OTLP gRPC receiver did not start; OTLP/HTTP remains available")
    yield
    if grpc_server is not None:
        grpc_server.stop(grace=1)
    close_redis()
    dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        summary="Self-hosted observability platform for logs, traces, metrics, and alerts.",
        description=OPENAPI_DESCRIPTION,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Project-Id", "Idempotency-Key", "X-Request-Id"],
        max_age=600,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        import uuid

        length = request.headers.get("content-length")
        if length:
            try:
                if int(length) > settings.max_body_bytes:
                    return JSONResponse(status_code=413, content={"detail": "Request body too large"})
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request failed",
                extra={"path": request.url.path, "method": request.method, "request_id": request_id},
            )
            return JSONResponse(status_code=500, content={"detail": "Internal server error"})
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path not in {"/health", "/ready"}:
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": safe_log_text(request.url.path),
                    "status_code": response.status_code,
                    "request_id": request_id,
                },
            )
        return response

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {"name": settings.app_name, "docs": "/docs", "health": "/health"}

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(projects.router)
    app.include_router(logs.router)
    app.include_router(events.router)
    app.include_router(traces.router)
    app.include_router(metrics.router)
    app.include_router(alerts.router)
    app.include_router(analytics.router)
    app.include_router(otlp.router)
    return app


app = create_app()
