from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query

from app.api.dependencies import DbSession, ProjectId
from app.core.config import get_settings
from app.schemas.common import resolve_window
from app.schemas.telemetry import ServiceOut
from app.services.analytics import AnalyticsService
from app.services.queries import QueryService

router = APIRouter(prefix="/api/v1", tags=["analytics"])


@router.get("/analytics/overview")
def overview(
    project_id: ProjectId,
    db: DbSession,
    start: datetime | None = Query(default=None, alias="from"),
    end: datetime | None = Query(default=None, alias="to"),
    range_key: str | None = Query(default="1h", alias="range"),
) -> dict:
    window_start, window_end = resolve_window(range_key, start, end)
    return AnalyticsService(db).overview(project_id, window_start, window_end)


@router.get("/analytics/breakdown")
def breakdown(
    project_id: ProjectId,
    db: DbSession,
    start: datetime | None = Query(default=None, alias="from"),
    end: datetime | None = Query(default=None, alias="to"),
    range_key: str | None = Query(default="1h", alias="range"),
) -> dict:
    window_start, window_end = resolve_window(range_key, start, end)
    return AnalyticsService(db).breakdown(project_id, window_start, window_end)


@router.get("/services", response_model=list[ServiceOut])
def services(
    project_id: ProjectId,
    db: DbSession,
    start: datetime | None = Query(default=None, alias="from"),
    end: datetime | None = Query(default=None, alias="to"),
    range_key: str | None = Query(default="1h", alias="range"),
) -> list[ServiceOut]:
    window_start, window_end = resolve_window(range_key, start, end)
    return QueryService(db).services(
        project_id,
        start=window_start,
        end=window_end,
        inactive_after=get_settings().service_inactive_seconds,
    )
