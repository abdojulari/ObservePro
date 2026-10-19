from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.api.dependencies import DbSession, IngestProjectId, ProjectId
from app.schemas.common import BatchResult, ItemError, Page, resolve_window
from app.schemas.telemetry import MetricBatchIn, MetricIn, MetricNameOut, MetricSampleOut, MetricSummaryOut, TimeseriesOut
from app.services.analytics import AnalyticsService
from app.services.ingestion import IngestError, IngestionService
from app.services.queries import QueryService

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


@router.post("", status_code=201)
def create_metric(body: MetricIn, project_id: IngestProjectId, db: DbSession) -> dict:
    try:
        outcome = IngestionService(db).ingest_metrics(project_id, [body])
    except IngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if outcome.accepted == 0:
        raise HTTPException(status_code=422, detail=outcome.errors)
    return {"id": outcome.ids[0], "accepted": outcome.accepted}


@router.post("/batch", response_model=BatchResult)
def create_metrics(body: MetricBatchIn, project_id: IngestProjectId, db: DbSession) -> BatchResult:
    try:
        outcome = IngestionService(db).ingest_metrics(project_id, body.metrics)
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


@router.get("/names", response_model=list[MetricNameOut])
def metric_names(project_id: ProjectId, db: DbSession) -> list[MetricNameOut]:
    return QueryService(db).metric_names(project_id)


@router.get("/timeseries", response_model=TimeseriesOut)
def metric_timeseries(
    project_id: ProjectId,
    db: DbSession,
    name: str,
    service: str | None = None,
    start: datetime | None = Query(default=None, alias="from"),
    end: datetime | None = Query(default=None, alias="to"),
    range_key: str | None = Query(default=None, alias="range"),
) -> TimeseriesOut:
    window_start, window_end = resolve_window(range_key, start, end)
    return TimeseriesOut(**AnalyticsService(db).metric_timeseries(project_id, name, window_start, window_end, service))


@router.get("/summary", response_model=MetricSummaryOut)
def metric_summary(
    project_id: ProjectId,
    db: DbSession,
    name: str,
    service: str | None = None,
    start: datetime | None = Query(default=None, alias="from"),
    end: datetime | None = Query(default=None, alias="to"),
    range_key: str | None = Query(default=None, alias="range"),
) -> MetricSummaryOut:
    window_start, window_end = resolve_window(range_key, start, end)
    return MetricSummaryOut(**AnalyticsService(db).metric_summary(project_id, name, window_start, window_end, service))


@router.get("", response_model=Page[MetricSampleOut])
def list_metrics(
    project_id: ProjectId,
    db: DbSession,
    name: str | None = None,
    service: str | None = None,
    start: datetime | None = Query(default=None, alias="from"),
    end: datetime | None = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[MetricSampleOut]:
    items, total = QueryService(db).metric_samples(
        project_id,
        name=name,
        service=service,
        start=start,
        end=end,
        page=page,
        page_size=page_size,
    )
    return Page(items=items, total=total, page=page, page_size=page_size)
