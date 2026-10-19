from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import EventRecord, LogEntry, MetricSample, ServiceRecord, TraceSpan, TraceSummary
from app.schemas.telemetry import (
    EventOut,
    LogOut,
    MetricNameOut,
    MetricSampleOut,
    ServiceOut,
    SpanOut,
    TraceDetail,
    TraceOut,
)
from app.services.ingestion import event_to_schema, log_to_schema


def like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class TelemetryRepository:
    def __init__(self, db: Session):
        self.db = db

    def logs(
        self,
        project_id: str,
        *,
        severity: str | None,
        service: str | None,
        environment: str | None,
        trace_id: str | None,
        q: str | None,
        start: datetime | None,
        end: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[LogOut], int]:
        conditions = [LogEntry.project_id == project_id]
        if severity:
            conditions.append(LogEntry.severity_text == severity.upper())
        if service:
            conditions.append(LogEntry.service == service)
        if environment:
            conditions.append(LogEntry.environment == environment)
        if trace_id:
            conditions.append(LogEntry.trace_id == trace_id.replace("-", "").lower())
        if q:
            pattern = like_pattern(q)
            conditions.append(
                or_(
                    LogEntry.message.ilike(pattern, escape="\\"),
                    LogEntry.service.ilike(pattern, escape="\\"),
                    func.cast(LogEntry.attributes, String).ilike(pattern, escape="\\"),
                )
            )
        if start:
            conditions.append(LogEntry.timestamp >= start)
        if end:
            conditions.append(LogEntry.timestamp <= end)
        where = and_(*conditions)
        total = int(self.db.scalar(select(func.count()).select_from(LogEntry).where(where)) or 0)
        rows = self.db.scalars(
            select(LogEntry)
            .where(where)
            .order_by(LogEntry.timestamp.desc(), LogEntry.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [log_to_schema(row) for row in rows], total

    def log(self, project_id: str, log_id: str) -> LogOut | None:
        row = self.db.scalar(select(LogEntry).where(LogEntry.project_id == project_id, LogEntry.id == log_id))
        return log_to_schema(row) if row else None

    def events(
        self,
        project_id: str,
        *,
        name: str | None,
        service: str | None,
        environment: str | None,
        start: datetime | None,
        end: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[EventOut], int]:
        conditions = [EventRecord.project_id == project_id]
        if name:
            conditions.append(EventRecord.name == name)
        if service:
            conditions.append(EventRecord.service == service)
        if environment:
            conditions.append(EventRecord.environment == environment)
        if start:
            conditions.append(EventRecord.timestamp >= start)
        if end:
            conditions.append(EventRecord.timestamp <= end)
        where = and_(*conditions)
        total = int(self.db.scalar(select(func.count()).select_from(EventRecord).where(where)) or 0)
        rows = self.db.scalars(
            select(EventRecord)
            .where(where)
            .order_by(EventRecord.timestamp.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [event_to_schema(row) for row in rows], total

    def traces(
        self,
        project_id: str,
        *,
        service: str | None,
        environment: str | None,
        status: str | None,
        start: datetime | None,
        end: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[TraceOut], int]:
        conditions = [TraceSummary.project_id == project_id]
        if service:
            conditions.append(TraceSummary.service == service)
        if environment:
            conditions.append(TraceSummary.environment == environment)
        if status:
            conditions.append(TraceSummary.status == status)
        if start:
            conditions.append(TraceSummary.start_time >= start)
        if end:
            conditions.append(TraceSummary.start_time <= end)
        where = and_(*conditions)
        total = int(self.db.scalar(select(func.count()).select_from(TraceSummary).where(where)) or 0)
        rows = self.db.scalars(
            select(TraceSummary)
            .where(where)
            .order_by(TraceSummary.start_time.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [self._trace(row) for row in rows], total

    def trace(self, project_id: str, trace_id: str) -> TraceDetail | None:
        normalized = trace_id.replace("-", "").lower()
        summary = self.db.scalar(
            select(TraceSummary).where(TraceSummary.project_id == project_id, TraceSummary.trace_id == normalized)
        )
        if summary is None:
            return None
        spans = self.db.scalars(
            select(TraceSpan)
            .where(TraceSpan.project_id == project_id, TraceSpan.trace_id == normalized)
            .order_by(TraceSpan.start_time.asc())
        ).all()
        logs, _total = self.logs(
            project_id,
            severity=None,
            service=None,
            environment=None,
            trace_id=normalized,
            q=None,
            start=None,
            end=None,
            page=1,
            page_size=200,
        )
        detail = TraceDetail(**self._trace(summary).model_dump(), spans=[self._span(row) for row in spans], logs=logs)
        return detail

    def spans(self, project_id: str, trace_id: str) -> list[SpanOut]:
        normalized = trace_id.replace("-", "").lower()
        rows = self.db.scalars(
            select(TraceSpan)
            .where(TraceSpan.project_id == project_id, TraceSpan.trace_id == normalized)
            .order_by(TraceSpan.start_time.asc())
        ).all()
        return [self._span(row) for row in rows]

    def metric_names(self, project_id: str) -> list[MetricNameOut]:
        rows = self.db.execute(
            select(MetricSample.name, MetricSample.metric_type, MetricSample.unit, MetricSample.description)
            .where(MetricSample.project_id == project_id)
            .group_by(MetricSample.name)
            .order_by(MetricSample.name.asc())
        ).all()
        return [
            MetricNameOut(name=name, type=metric_type, unit=unit, description=description)
            for name, metric_type, unit, description in rows
        ]

    def metric_samples(
        self,
        project_id: str,
        *,
        name: str | None,
        service: str | None,
        start: datetime | None,
        end: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[MetricSampleOut], int]:
        conditions = [MetricSample.project_id == project_id]
        if name:
            conditions.append(MetricSample.name == name)
        if service:
            conditions.append(MetricSample.service == service)
        if start:
            conditions.append(MetricSample.timestamp >= start)
        if end:
            conditions.append(MetricSample.timestamp <= end)
        where = and_(*conditions)
        total = int(self.db.scalar(select(func.count()).select_from(MetricSample).where(where)) or 0)
        rows = self.db.scalars(
            select(MetricSample)
            .where(where)
            .order_by(MetricSample.timestamp.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [self._metric(row) for row in rows], total

    def services(self, project_id: str, *, start: datetime, end: datetime, inactive_after: int) -> list[ServiceOut]:
        rows = self.db.scalars(
            select(ServiceRecord).where(ServiceRecord.project_id == project_id).order_by(ServiceRecord.name.asc())
        ).all()
        results: list[ServiceOut] = []
        for row in rows:
            log_count = int(
                self.db.scalar(
                    select(func.count())
                    .select_from(LogEntry)
                    .where(
                        LogEntry.project_id == project_id,
                        LogEntry.service == row.name,
                        LogEntry.environment == row.environment,
                        LogEntry.timestamp >= start,
                        LogEntry.timestamp <= end,
                    )
                )
                or 0
            )
            error_count = int(
                self.db.scalar(
                    select(func.count())
                    .select_from(LogEntry)
                    .where(
                        LogEntry.project_id == project_id,
                        LogEntry.service == row.name,
                        LogEntry.environment == row.environment,
                        LogEntry.severity_number >= 17,
                        LogEntry.timestamp >= start,
                        LogEntry.timestamp <= end,
                    )
                )
                or 0
            )
            span_count = int(
                self.db.scalar(
                    select(func.count())
                    .select_from(TraceSpan)
                    .where(
                        TraceSpan.project_id == project_id,
                        TraceSpan.service == row.name,
                        TraceSpan.start_time >= start,
                        TraceSpan.start_time <= end,
                    )
                )
                or 0
            )
            age = (end - row.last_seen).total_seconds() if row.last_seen <= end else 0
            if (end - row.last_seen).total_seconds() > inactive_after:
                health = "inactive"
            elif log_count and error_count / log_count >= 0.05:
                health = "degraded"
            elif log_count or span_count:
                health = "healthy"
            else:
                health = "unknown" if age > inactive_after else "healthy"
            results.append(
                ServiceOut(
                    name=row.name,
                    environment=row.environment,
                    version=row.version,
                    first_seen=row.first_seen,
                    last_seen=row.last_seen,
                    health=health,
                    log_count=log_count,
                    error_count=error_count,
                    span_count=span_count,
                )
            )
        return results

    @staticmethod
    def _trace(row: TraceSummary) -> TraceOut:
        return TraceOut(
            trace_id=row.trace_id,
            root_span_name=row.root_span_name,
            service=row.service,
            environment=row.environment,
            start_time=row.start_time,
            end_time=row.end_time,
            duration_ms=row.duration_ms,
            span_count=row.span_count,
            error_count=row.error_count,
            status=row.status,
        )

    @staticmethod
    def _span(row: TraceSpan) -> SpanOut:
        return SpanOut(
            id=row.id,
            trace_id=row.trace_id,
            span_id=row.span_id,
            parent_span_id=row.parent_span_id,
            name=row.name,
            kind=row.kind,
            start_time=row.start_time,
            end_time=row.end_time,
            duration_ms=row.duration_ms,
            status_code=row.status_code,
            status_message=row.status_message,
            service=row.service,
            environment=row.environment,
            attributes=row.attributes or {},
            events=row.events or [],
            links=row.links or [],
            resource_attributes=row.resource_attributes or {},
        )

    @staticmethod
    def _metric(row: MetricSample) -> MetricSampleOut:
        return MetricSampleOut(
            id=row.id,
            name=row.name,
            type=row.metric_type,
            temporality=row.temporality,
            timestamp=row.timestamp,
            service=row.service,
            environment=row.environment,
            value=row.value,
            count=row.count,
            sum=row.sum,
            min=row.min,
            max=row.max,
            unit=row.unit,
            bucket_bounds=row.bucket_bounds,
            bucket_counts=row.bucket_counts,
            attributes=row.attributes or {},
        )
