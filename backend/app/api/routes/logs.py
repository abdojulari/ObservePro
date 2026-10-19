from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from app.api.dependencies import DbSession, IngestProjectId, ProjectId
from app.schemas.common import BatchResult, ItemError, Page
from app.schemas.telemetry import LogBatchIn, LogIn, LogOut
from app.services.ingestion import IngestError, IngestOutcome, IngestionService
from app.services.queries import QueryService

router = APIRouter(prefix="/api/v1/logs", tags=["logs"])


def _finish(outcome: IngestOutcome, *, many: bool):
    if outcome.replay_body is not None:
        return JSONResponse(status_code=outcome.replay_status or 200, content=outcome.replay_body)
    if outcome.accepted == 0:
        raise HTTPException(status_code=422, detail=outcome.errors or "No logs were accepted")
    if many:
        return BatchResult(
            accepted=outcome.accepted,
            rejected=outcome.rejected,
            errors=[ItemError(**error) for error in outcome.errors],
            ids=outcome.ids,
        )
    return outcome.logs[0]


@router.post("", response_model=LogOut, status_code=201, summary="Ingest one log record")
def create_log(
    body: LogIn,
    project_id: IngestProjectId,
    db: DbSession,
    idempotency_key: str | None = Header(default=None),
):
    try:
        outcome = IngestionService(db).ingest_logs(
            project_id,
            [body],
            idempotency_key=idempotency_key,
            idempotency_payload=body.model_dump(mode="json"),
        )
    except IngestError as exc:
        status = 409 if "idempotency" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return _finish(outcome, many=False)


@router.post("/batch", response_model=BatchResult, summary="Ingest a batch of log records")
def create_logs(
    body: LogBatchIn,
    project_id: IngestProjectId,
    db: DbSession,
    idempotency_key: str | None = Header(default=None),
):
    try:
        outcome = IngestionService(db).ingest_logs(
            project_id,
            body.logs,
            idempotency_key=idempotency_key,
            idempotency_payload=body.model_dump(mode="json"),
            idempotency_status=200,
        )
    except IngestError as exc:
        status = 409 if "idempotency" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return _finish(outcome, many=True)


@router.get("", response_model=Page[LogOut], summary="Search logs for the authenticated project")
def list_logs(
    project_id: ProjectId,
    db: DbSession,
    severity: str | None = None,
    service: str | None = None,
    environment: str | None = None,
    trace_id: str | None = None,
    q: str | None = None,
    start: datetime | None = Query(default=None, alias="from"),
    end: datetime | None = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[LogOut]:
    items, total = QueryService(db).logs(
        project_id,
        severity=severity,
        service=service,
        environment=environment,
        trace_id=trace_id,
        q=q,
        start=start,
        end=end,
        page=page,
        page_size=page_size,
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{log_id}", response_model=LogOut)
def get_log(log_id: str, project_id: ProjectId, db: DbSession) -> LogOut:
    row = QueryService(db).log(project_id, log_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Log not found")
    return row
