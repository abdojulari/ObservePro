from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.api.dependencies import DbSession, ProjectId
from app.schemas.common import Page
from app.schemas.telemetry import SpanOut, TraceDetail, TraceOut
from app.services.queries import QueryService

router = APIRouter(prefix="/api/v1/traces", tags=["traces"])


@router.get("", response_model=Page[TraceOut])
def list_traces(
    project_id: ProjectId,
    db: DbSession,
    service: str | None = None,
    environment: str | None = None,
    status: str | None = None,
    start: datetime | None = Query(default=None, alias="from"),
    end: datetime | None = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[TraceOut]:
    items, total = QueryService(db).traces(
        project_id,
        service=service,
        environment=environment,
        status=status,
        start=start,
        end=end,
        page=page,
        page_size=page_size,
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{trace_id}/spans", response_model=list[SpanOut])
def list_spans(trace_id: str, project_id: ProjectId, db: DbSession) -> list[SpanOut]:
    return QueryService(db).spans(project_id, trace_id)


@router.get("/{trace_id}", response_model=TraceDetail)
def get_trace(trace_id: str, project_id: ProjectId, db: DbSession) -> TraceDetail:
    detail = QueryService(db).trace(project_id, trace_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return detail
