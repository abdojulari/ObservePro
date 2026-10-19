from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.api.dependencies import DbSession, IngestProjectId, ProjectId
from app.schemas.common import BatchResult, ItemError, Page
from app.schemas.telemetry import EventBatchIn, EventIn, EventOut
from app.services.ingestion import IngestError, IngestionService
from app.services.queries import QueryService

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.post("", response_model=EventOut, status_code=201)
def create_event(body: EventIn, project_id: IngestProjectId, db: DbSession) -> EventOut:
    try:
        outcome = IngestionService(db).ingest_events(project_id, [body])
    except IngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not outcome.events:
        raise HTTPException(status_code=422, detail=outcome.errors)
    return outcome.events[0]


@router.post("/batch", response_model=BatchResult)
def create_events(body: EventBatchIn, project_id: IngestProjectId, db: DbSession) -> BatchResult:
    try:
        outcome = IngestionService(db).ingest_events(project_id, body.events)
    except IngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if outcome.accepted == 0:
        raise HTTPException(status_code=422, detail=outcome.errors)
    return BatchResult(
        accepted=outcome.accepted,
        rejected=outcome.rejected,
        errors=[ItemError(**error) for error in outcome.errors],
        ids=outcome.ids,
    )


@router.get("", response_model=Page[EventOut])
def list_events(
    project_id: ProjectId,
    db: DbSession,
    name: str | None = None,
    service: str | None = None,
    environment: str | None = None,
    start: datetime | None = Query(default=None, alias="from"),
    end: datetime | None = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[EventOut]:
    items, total = QueryService(db).events(
        project_id,
        name=name,
        service=service,
        environment=environment,
        start=start,
        end=end,
        page=page,
        page_size=page_size,
    )
    return Page(items=items, total=total, page=page, page_size=page_size)
