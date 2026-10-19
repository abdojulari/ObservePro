from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.db.session import check_database
from app.services.redis_client import redis_state

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
def health() -> dict:
    settings = get_settings()
    return {"status": "ok", "service": settings.app_name, "version": settings.app_version}


@router.get("/ready", summary="Readiness probe")
def ready(request: Request) -> dict:
    database_ok = check_database()
    state = redis_state()
    body = {
        "status": "ready" if database_ok else "not_ready",
        "database": "ok" if database_ok else "down",
        "redis": state if state != "unconfigured" else "degraded",
    }
    if not database_ok:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content=body)
    return body
