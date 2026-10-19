from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from app.api.dependencies import DbSession, IngestProjectId
from app.core.config import get_settings
from app.services.ingestion import IngestError, IngestionService
from app.telemetry.otlp import (
    logs_from_json,
    logs_from_protobuf,
    metrics_from_json,
    metrics_from_protobuf,
    protobuf_response,
    spans_from_json,
    spans_from_protobuf,
)

router = APIRouter(tags=["otlp"])


async def raw_body(request: Request) -> bytes:
    payload = await request.body()
    if len(payload) > get_settings().max_body_bytes:
        raise HTTPException(status_code=413, detail="Request body too large")
    return payload


def _is_json(request: Request) -> bool:
    content_type = request.headers.get("content-type", "")
    return "json" in content_type


@router.post("/v1/traces", summary="OTLP/HTTP trace export")
def export_traces(request: Request, project_id: IngestProjectId, db: DbSession, payload: bytes = Depends(raw_body)):
    try:
        spans = spans_from_json(json.loads(payload)) if _is_json(request) else spans_from_protobuf(payload)
        outcome = IngestionService(db).ingest_spans(project_id, spans)
    except (IngestError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse OTLP traces: {exc}") from exc
    if _is_json(request):
        return JSONResponse(_partial("rejectedSpans", outcome.rejected))
    return Response(content=protobuf_response("traces", outcome.rejected), media_type="application/x-protobuf")


@router.post("/v1/metrics", summary="OTLP/HTTP metric export")
def export_metrics(request: Request, project_id: IngestProjectId, db: DbSession, payload: bytes = Depends(raw_body)):
    try:
        metrics = metrics_from_json(json.loads(payload)) if _is_json(request) else metrics_from_protobuf(payload)
        outcome = IngestionService(db).ingest_metrics(project_id, metrics)
    except (IngestError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse OTLP metrics: {exc}") from exc
    if _is_json(request):
        return JSONResponse(_partial("rejectedDataPoints", outcome.rejected))
    return Response(content=protobuf_response("metrics", outcome.rejected), media_type="application/x-protobuf")


@router.post("/v1/logs", summary="OTLP/HTTP log export")
def export_logs(request: Request, project_id: IngestProjectId, db: DbSession, payload: bytes = Depends(raw_body)):
    try:
        logs = logs_from_json(json.loads(payload)) if _is_json(request) else logs_from_protobuf(payload)
        outcome = IngestionService(db).ingest_logs(project_id, logs)
    except (IngestError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse OTLP logs: {exc}") from exc
    if _is_json(request):
        return JSONResponse(_partial("rejectedLogRecords", outcome.rejected))
    return Response(content=protobuf_response("logs", outcome.rejected), media_type="application/x-protobuf")


def _partial(field: str, rejected: int) -> dict:
    if not rejected:
        return {}
    return {"partialSuccess": {field: rejected, "errorMessage": f"{rejected} item(s) were rejected"}}
