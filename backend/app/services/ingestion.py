from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.redaction import redact
from app.core.security import utcnow
from app.models import (
    EventRecord,
    IdempotencyRecord,
    LogEntry,
    MetricSample,
    PlatformCounter,
    ServiceRecord,
    TraceSpan,
    TraceSummary,
)
from app.schemas.telemetry import EventIn, EventOut, LogIn, LogOut, MetricIn
from app.telemetry.otlp import IncomingSpan
from app.telemetry.severity import normalize_severity


class IngestError(ValueError):
    pass


class IngestOutcome:
    def __init__(self) -> None:
        self.ids: list[str] = []
        self.errors: list[dict[str, object]] = []
        self.logs: list[LogOut] = []
        self.events: list[EventOut] = []
        self.replay_status: int | None = None
        self.replay_body: object | None = None

    @property
    def accepted(self) -> int:
        return len(self.ids)

    @property
    def rejected(self) -> int:
        return len(self.errors)


def clamp_timestamp(value: datetime | None) -> datetime:
    now = utcnow()
    if value is None:
        return now
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    if value < datetime(2000, 1, 1, tzinfo=timezone.utc):
        raise IngestError("timestamp is too far in the past")
    if value > now + timedelta(days=1):
        raise IngestError("timestamp is too far in the future")
    return value


def clean_identifier(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    cleaned = value.replace("-", "").strip().lower()
    cleaned = "".join(char for char in cleaned if char.isprintable())
    return cleaned[:limit] or None


def attribute_hash(attributes: dict) -> str:
    raw = json.dumps(attributes, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def body_hash(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def bump(db: Session, key: str, amount: int = 1) -> None:
    row = db.get(PlatformCounter, key)
    if row is None:
        db.add(PlatformCounter(key=key, value=amount))
    else:
        row.value += amount


def touch_service(
    db: Session,
    project_id: str,
    name: str | None,
    environment: str | None,
    version: str | None = None,
    seen_at: datetime | None = None,
) -> None:
    service_name = (name or "unknown")[:200]
    service_env = (environment or "production")[:100]
    moment = seen_at or utcnow()
    try:
        with db.begin_nested():
            row = db.scalar(
                select(ServiceRecord).where(
                    ServiceRecord.project_id == project_id,
                    ServiceRecord.name == service_name,
                    ServiceRecord.environment == service_env,
                )
            )
            if row is None:
                db.add(
                    ServiceRecord(
                        project_id=project_id,
                        name=service_name,
                        environment=service_env,
                        version=version,
                        first_seen=moment,
                        last_seen=moment,
                    )
                )
                db.flush()
                return
            if moment > row.last_seen:
                row.last_seen = moment
            if version:
                row.version = version
    except IntegrityError:
        row = db.scalar(
            select(ServiceRecord).where(
                ServiceRecord.project_id == project_id,
                ServiceRecord.name == service_name,
                ServiceRecord.environment == service_env,
            )
        )
        if row is not None and moment > row.last_seen:
            row.last_seen = moment


def log_to_schema(row: LogEntry) -> LogOut:
    exception = None
    if row.exception_type or row.exception_message or row.stack_trace:
        from app.schemas.telemetry import ExceptionOut

        exception = ExceptionOut(
            type=row.exception_type,
            message=row.exception_message,
            stacktrace=row.stack_trace,
        )
    return LogOut(
        id=row.id,
        project_id=row.project_id,
        timestamp=row.timestamp,
        ingested_at=row.ingested_at,
        severity=row.severity_text,
        severity_number=row.severity_number,
        message=row.message,
        service=row.service,
        environment=row.environment,
        logger=row.logger_name,
        trace_id=row.trace_id,
        span_id=row.span_id,
        request_id=row.request_id,
        hostname=row.hostname,
        version=row.app_version,
        source_file=row.source_file,
        source_line=row.source_line,
        attributes=row.attributes or {},
        exception=exception,
        event_id=row.event_id,
    )


def event_to_schema(row: EventRecord) -> EventOut:
    return EventOut(
        id=row.id,
        project_id=row.project_id,
        timestamp=row.timestamp,
        name=row.name,
        message=row.message,
        service=row.service,
        environment=row.environment,
        attributes=row.attributes or {},
    )


class IngestionService:
    def __init__(self, db: Session):
        self.db = db

    def ingest_logs(
        self,
        project_id: str,
        items: list[LogIn],
        *,
        idempotency_key: str | None = None,
        idempotency_payload: object | None = None,
        idempotency_status: int = 201,
    ) -> IngestOutcome:
        outcome = IngestOutcome()
        if idempotency_key:
            replay = self._replay(project_id, idempotency_key, idempotency_payload)
            if replay is not None:
                return replay
        for index, item in enumerate(items):
            try:
                with self.db.begin_nested():
                    if item.event_id:
                        existing = self.db.scalar(
                            select(LogEntry).where(
                                LogEntry.project_id == project_id,
                                LogEntry.event_id == item.event_id,
                            )
                        )
                        if existing is not None:
                            outcome.ids.append(existing.id)
                            outcome.logs.append(log_to_schema(existing))
                            continue
                    row = self._build_log(project_id, item)
                    self.db.add(row)
                    self.db.flush()
                    touch_service(
                        self.db,
                        project_id,
                        row.service,
                        row.environment,
                        row.app_version,
                        row.timestamp,
                    )
                    outcome.ids.append(row.id)
                    outcome.logs.append(log_to_schema(row))
            except IngestError as exc:
                outcome.errors.append({"index": index, "detail": str(exc)})
            except IntegrityError:
                existing = None
                if item.event_id:
                    existing = self.db.scalar(
                        select(LogEntry).where(
                            LogEntry.project_id == project_id,
                            LogEntry.event_id == item.event_id,
                        )
                    )
                if existing is not None:
                    outcome.ids.append(existing.id)
                    outcome.logs.append(log_to_schema(existing))
                else:
                    outcome.errors.append({"index": index, "detail": "duplicate log was rejected"})
        if outcome.accepted:
            bump(self.db, "logs_accepted", outcome.accepted)
        if outcome.rejected:
            bump(self.db, "logs_rejected", outcome.rejected)
        if idempotency_key and outcome.accepted:
            self._store_idempotency(
                project_id, idempotency_key, idempotency_payload, idempotency_status, outcome
            )
        return outcome

    def ingest_events(self, project_id: str, items: list[EventIn]) -> IngestOutcome:
        outcome = IngestOutcome()
        for index, item in enumerate(items):
            try:
                with self.db.begin_nested():
                    timestamp = clamp_timestamp(item.timestamp)
                    row = EventRecord(
                        project_id=project_id,
                        timestamp=timestamp,
                        name=item.name.replace("\x00", ""),
                        message=item.message.replace("\x00", "") if item.message else None,
                        service=item.service or "unknown",
                        environment=item.environment or "production",
                        attributes=redact(item.attributes),
                    )
                    self.db.add(row)
                    self.db.flush()
                    touch_service(self.db, project_id, row.service, row.environment, seen_at=timestamp)
                    outcome.ids.append(row.id)
                    outcome.events.append(event_to_schema(row))
            except IngestError as exc:
                outcome.errors.append({"index": index, "detail": str(exc)})
        if outcome.accepted:
            bump(self.db, "events_accepted", outcome.accepted)
        if outcome.rejected:
            bump(self.db, "events_rejected", outcome.rejected)
        return outcome

    def ingest_metrics(self, project_id: str, items: list[MetricIn]) -> IngestOutcome:
        outcome = IngestOutcome()
        for index, item in enumerate(items):
            try:
                with self.db.begin_nested():
                    row = self._build_metric(project_id, item)
                    if row.temporality == "cumulative":
                        existing = self.db.scalar(
                            select(MetricSample).where(
                                MetricSample.project_id == project_id,
                                MetricSample.name == row.name,
                                MetricSample.service == row.service,
                                MetricSample.environment == row.environment,
                                MetricSample.timestamp == row.timestamp,
                                MetricSample.attr_hash == row.attr_hash,
                            )
                        )
                        if existing is not None:
                            existing.value = row.value
                            existing.count = row.count
                            existing.sum = row.sum
                            existing.min = row.min
                            existing.max = row.max
                            existing.bucket_bounds = row.bucket_bounds
                            existing.bucket_counts = row.bucket_counts
                            outcome.ids.append(existing.id)
                            touch_service(self.db, project_id, row.service, row.environment, seen_at=row.timestamp)
                            continue
                    self.db.add(row)
                    self.db.flush()
                    touch_service(self.db, project_id, row.service, row.environment, seen_at=row.timestamp)
                    outcome.ids.append(row.id)
            except IngestError as exc:
                outcome.errors.append({"index": index, "detail": str(exc)})
        if outcome.accepted:
            bump(self.db, "metrics_accepted", outcome.accepted)
        if outcome.rejected:
            bump(self.db, "metrics_rejected", outcome.rejected)
        return outcome

    def ingest_spans(self, project_id: str, spans: list[IncomingSpan]) -> IngestOutcome:
        outcome = IngestOutcome()
        touched: set[str] = set()
        for index, span in enumerate(spans):
            try:
                with self.db.begin_nested():
                    if not span.trace_id or not span.span_id:
                        raise IngestError("span is missing a trace id or span id")
                    start = clamp_timestamp(span.start_time)
                    end = clamp_timestamp(span.end_time)
                    if end < start:
                        end = start
                    duration_ms = (end - start).total_seconds() * 1000
                    attributes = redact(span.attributes)
                    existing = self.db.scalar(
                        select(TraceSpan).where(
                            TraceSpan.project_id == project_id,
                            TraceSpan.trace_id == span.trace_id,
                            TraceSpan.span_id == span.span_id,
                        )
                    )
                    if existing is None:
                        existing = TraceSpan(
                            project_id=project_id,
                            trace_id=span.trace_id,
                            span_id=span.span_id,
                        )
                        self.db.add(existing)
                    existing.parent_span_id = span.parent_span_id
                    existing.name = (span.name or "span")[:500]
                    existing.kind = span.kind
                    existing.start_time = start
                    existing.end_time = end
                    existing.duration_ms = duration_ms
                    existing.status_code = span.status_code
                    existing.status_message = span.status_message
                    existing.service = span.service or "unknown"
                    existing.environment = span.environment
                    existing.attributes = attributes
                    existing.events = redact(span.events)
                    existing.links = redact(span.links)
                    existing.resource_attributes = redact(span.resource_attributes)
                    self.db.flush()
                    touch_service(
                        self.db,
                        project_id,
                        existing.service,
                        existing.environment,
                        span.version,
                        seen_at=end,
                    )
                    outcome.ids.append(existing.id)
                    touched.add(span.trace_id)
            except IngestError as exc:
                outcome.errors.append({"index": index, "detail": str(exc)})
        for trace_id in touched:
            self._refresh_trace(project_id, trace_id)
        if outcome.accepted:
            bump(self.db, "spans_accepted", outcome.accepted)
        if outcome.rejected:
            bump(self.db, "spans_rejected", outcome.rejected)
        return outcome

    def _build_log(self, project_id: str, item: LogIn) -> LogEntry:
        severity, number = normalize_severity(item.severity, item.severity_number)
        exception = item.exception
        return LogEntry(
            project_id=project_id,
            timestamp=clamp_timestamp(item.timestamp),
            severity_text=severity,
            severity_number=number,
            message=item.message.replace("\x00", ""),
            service=item.service or "unknown",
            environment=item.environment or "production",
            logger_name=item.logger,
            trace_id=clean_identifier(item.trace_id, 64),
            span_id=clean_identifier(item.span_id, 32),
            request_id=item.request_id,
            hostname=item.hostname,
            app_version=item.version,
            source_file=item.source_file,
            source_line=item.source_line,
            attributes=redact(item.attributes),
            exception_type=exception.type if exception else None,
            exception_message=exception.message.replace("\x00", "") if exception and exception.message else None,
            stack_trace=exception.stacktrace if exception else None,
            event_id=item.event_id,
        )

    def _build_metric(self, project_id: str, item: MetricIn) -> MetricSample:
        timestamp = clamp_timestamp(item.timestamp)
        attributes = redact(item.attributes)
        bounds = list(item.bucket_bounds) if item.bucket_bounds is not None else None
        counts = list(item.bucket_counts) if item.bucket_counts is not None else None
        value = item.value
        count = item.count
        total = item.sum
        if item.type in {"histogram", "exponential_histogram"} and value is not None and not counts:
            bounds = [float(value)]
            counts = [1, 0]
            count = 1
            total = float(value)
        return MetricSample(
            project_id=project_id,
            name=item.name,
            description=item.description,
            unit=item.unit,
            metric_type=item.type,
            temporality=item.temporality,
            timestamp=timestamp,
            service=item.service or "unknown",
            environment=item.environment or "production",
            value=value,
            count=count,
            sum=total,
            min=item.min if item.min is not None else value,
            max=item.max if item.max is not None else value,
            bucket_bounds=bounds,
            bucket_counts=counts,
            attributes=attributes,
            attr_hash=attribute_hash(attributes),
            is_monotonic=item.is_monotonic,
        )

    def _refresh_trace(self, project_id: str, trace_id: str) -> None:
        spans = list(
            self.db.scalars(
                select(TraceSpan).where(TraceSpan.project_id == project_id, TraceSpan.trace_id == trace_id)
            ).all()
        )
        if not spans:
            return
        start = min(span.start_time for span in spans)
        end = max(span.end_time for span in spans)
        errors = sum(1 for span in spans if span.status_code == "error")
        roots = [span for span in spans if not span.parent_span_id]
        root = min(roots or spans, key=lambda span: span.start_time)
        summary = self.db.scalar(
            select(TraceSummary).where(TraceSummary.project_id == project_id, TraceSummary.trace_id == trace_id)
        )
        if summary is None:
            summary = TraceSummary(project_id=project_id, trace_id=trace_id, start_time=start, end_time=end)
            self.db.add(summary)
        summary.root_span_name = root.name
        summary.service = root.service
        summary.environment = root.environment
        summary.start_time = start
        summary.end_time = end
        summary.duration_ms = max(0.0, (end - start).total_seconds() * 1000)
        summary.span_count = len(spans)
        summary.error_count = errors
        summary.status = "error" if errors else "ok"

    def _replay(self, project_id: str, key: str, payload: object | None) -> IngestOutcome | None:
        row = self.db.scalar(
            select(IdempotencyRecord).where(IdempotencyRecord.project_id == project_id, IdempotencyRecord.key == key)
        )
        if row is None:
            return None
        digest = body_hash(payload)
        if row.body_hash != digest:
            raise IngestError("idempotency key was already used with a different payload")
        outcome = IngestOutcome()
        outcome.replay_status = row.status_code
        outcome.replay_body = json.loads(row.response_json)
        return outcome

    def _store_idempotency(
        self,
        project_id: str,
        key: str,
        payload: object | None,
        status_code: int,
        outcome: IngestOutcome,
    ) -> None:
        body = {
            "accepted": outcome.accepted,
            "rejected": outcome.rejected,
            "errors": outcome.errors,
            "ids": outcome.ids,
        }
        if len(outcome.logs) == 1 and outcome.rejected == 0:
            body = outcome.logs[0].model_dump(mode="json")
        self.db.add(
            IdempotencyRecord(
                project_id=project_id,
                key=key[:200],
                body_hash=body_hash(payload),
                status_code=status_code,
                response_json=json.dumps(body, default=str),
            )
        )
