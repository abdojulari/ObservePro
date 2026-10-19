from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import Integer, case, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AlertIncident, LogEntry, MetricSample, TraceSpan
from app.schemas.common import bucket_seconds
from app.services.queries import QueryService
from app.services.redis_client import cache_get, cache_set
from app.telemetry.histogram import histogram_quantile, merge_histograms, percentile


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def bucket_label(column, seconds: int):
    if seconds <= 60:
        return func.strftime("%Y-%m-%dT%H:%M:00Z", column)
    if seconds <= 300:
        minute = func.cast(func.strftime("%M", column), Integer)
        floored = func.cast(minute / 5, Integer) * 5
        return func.strftime("%Y-%m-%dT%H:", column) + func.printf("%02d", floored) + ":00Z"
    if seconds <= 3600:
        return func.strftime("%Y-%m-%dT%H:00:00Z", column)
    hour = func.cast(func.strftime("%H", column), Integer)
    floored = func.cast(hour / 6, Integer) * 6
    return func.strftime("%Y-%m-%dT", column) + func.printf("%02d", floored) + ":00:00Z"


class AnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    def overview(self, project_id: str, start: datetime, end: datetime) -> dict:
        start = _aware(start)
        end = _aware(end)
        cache_key = f"overview:{project_id}:{start.isoformat()}:{end.isoformat()}"
        cached = cache_get(cache_key)
        if cached is not None:
            return cached
        payload = {
            "range": {"start": start.isoformat(), "end": end.isoformat()},
            "logs": self._log_stats(project_id, start, end),
            "alerts": self._alert_counts(project_id),
            "traffic": self._traffic(project_id, start, end),
            "ingestion": self._ingestion(project_id, start, end),
            "services": [
                item.model_dump(mode="json")
                for item in QueryService(self.db).services(
                    project_id,
                    start=start,
                    end=end,
                    inactive_after=get_settings().service_inactive_seconds,
                )
            ],
            "recent_errors": [
                item.model_dump(mode="json")
                for item in self._recent_errors(project_id, start, end)
            ],
            "recent_alerts": self._recent_alerts(project_id),
        }
        cache_set(cache_key, payload, ttl_seconds=10)
        return payload

    def breakdown(self, project_id: str, start: datetime, end: datetime) -> dict:
        start = _aware(start)
        end = _aware(end)
        return {
            "range": {"start": start.isoformat(), "end": end.isoformat()},
            "log_volume": self._count_series(project_id, start, end, minimum_severity=None),
            "error_volume": self._count_series(project_id, start, end, minimum_severity=17),
            "severity": self._severity(project_id, start, end),
            "errors_by_service": self._grouped(project_id, start, end, LogEntry.service, minimum_severity=17),
            "active_services": self._grouped(project_id, start, end, LogEntry.service, minimum_severity=None),
            "top_errors": self._top_messages(project_id, start, end),
            "alert_trend": self._alert_trend(project_id, start, end),
            "latency_buckets": self._latency_buckets(project_id, start, end),
            "service_comparison": self._service_comparison(project_id, start, end),
        }

    def metric_summary(self, project_id: str, name: str, start: datetime, end: datetime, service: str | None) -> dict:
        samples = self._samples(project_id, name, start, end, service)
        if not samples:
            return {
                "name": name,
                "type": "gauge",
                "count": 0,
                "sum": None,
                "min": None,
                "max": None,
                "avg": None,
                "rate": None,
                "p50": None,
                "p95": None,
                "p99": None,
                "approximate": False,
                "sample_count": 0,
            }
        metric_type = samples[-1].metric_type
        window = max(1.0, (_aware(end) - _aware(start)).total_seconds())
        if metric_type in {"histogram", "exponential_histogram"}:
            bounds, counts, approximate = self._merge_sample_histograms(samples)
            total = sum(counts) if counts else sum(sample.count or 0 for sample in samples)
            summed = sum(sample.sum or 0 for sample in samples if sample.temporality != "cumulative")
            if any(sample.temporality == "cumulative" for sample in samples):
                summed = samples[-1].sum
            return {
                "name": name,
                "type": metric_type,
                "count": int(total),
                "sum": summed,
                "min": min((sample.min for sample in samples if sample.min is not None), default=None),
                "max": max((sample.max for sample in samples if sample.max is not None), default=None),
                "avg": (summed / total) if summed is not None and total else None,
                "rate": (total / window) if total else 0,
                "p50": histogram_quantile(0.50, bounds, counts) if counts else None,
                "p95": histogram_quantile(0.95, bounds, counts) if counts else None,
                "p99": histogram_quantile(0.99, bounds, counts) if counts else None,
                "approximate": approximate,
                "sample_count": len(samples),
            }
        values = [float(sample.value) for sample in samples if sample.value is not None]
        if metric_type == "counter":
            rate = self._counter_rate(samples, window)
            return {
                "name": name,
                "type": metric_type,
                "count": len(values),
                "sum": sum(values) if values else None,
                "min": min(values) if values else None,
                "max": max(values) if values else None,
                "avg": (sum(values) / len(values)) if values else None,
                "rate": rate,
                "p50": None,
                "p95": None,
                "p99": None,
                "approximate": False,
                "sample_count": len(samples),
            }
        return {
            "name": name,
            "type": metric_type,
            "count": len(values),
            "sum": sum(values) if values else None,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "avg": (sum(values) / len(values)) if values else None,
            "rate": None,
            "p50": percentile(values, 0.50),
            "p95": percentile(values, 0.95),
            "p99": percentile(values, 0.99),
            "approximate": False,
            "sample_count": len(values),
        }

    def metric_timeseries(
        self,
        project_id: str,
        name: str,
        start: datetime,
        end: datetime,
        service: str | None,
    ) -> dict:
        samples = self._samples(project_id, name, start, end, service)
        seconds = bucket_seconds(_aware(start), _aware(end))
        grouped: dict[str, list[MetricSample]] = {}
        for sample in samples:
            label = self._python_bucket(sample.timestamp, seconds)
            grouped.setdefault(label, []).append(sample)
        metric_type = samples[-1].metric_type if samples else "gauge"
        points = []
        approximate = False
        for label in sorted(grouped):
            bucket_samples = grouped[label]
            if metric_type in {"histogram", "exponential_histogram"}:
                bounds, counts, approx = self._merge_sample_histograms(bucket_samples)
                approximate = approximate or approx
                total = sum(counts) if counts else 0
                summed = sum(sample.sum or 0 for sample in bucket_samples)
                points.append(
                    {
                        "timestamp": label,
                        "value": None,
                        "count": total,
                        "sum": summed,
                        "avg": (summed / total) if total else None,
                        "p50": histogram_quantile(0.50, bounds, counts) if counts else None,
                        "p95": histogram_quantile(0.95, bounds, counts) if counts else None,
                        "p99": histogram_quantile(0.99, bounds, counts) if counts else None,
                    }
                )
            else:
                values = [float(sample.value) for sample in bucket_samples if sample.value is not None]
                points.append(
                    {
                        "timestamp": label,
                        "value": (sum(values) / len(values)) if values else None,
                        "count": len(values),
                        "sum": sum(values) if values else None,
                        "avg": (sum(values) / len(values)) if values else None,
                        "p50": percentile(values, 0.50),
                        "p95": percentile(values, 0.95),
                        "p99": percentile(values, 0.99),
                    }
                )
        return {
            "name": name,
            "type": metric_type,
            "service": service,
            "points": points,
            "approximate": approximate,
        }

    def _samples(self, project_id: str, name: str, start: datetime, end: datetime, service: str | None) -> list[MetricSample]:
        stmt = (
            select(MetricSample)
            .where(
                MetricSample.project_id == project_id,
                MetricSample.name == name,
                MetricSample.timestamp >= start,
                MetricSample.timestamp <= end,
            )
            .order_by(MetricSample.timestamp.asc())
            .limit(20_000)
        )
        if service:
            stmt = stmt.where(MetricSample.service == service)
        return list(self.db.scalars(stmt).all())

    def _merge_sample_histograms(self, samples: list[MetricSample]) -> tuple[list[float], list[int], bool]:
        series: dict[tuple, list[MetricSample]] = {}
        for sample in samples:
            series.setdefault((sample.service, sample.environment, sample.attr_hash), []).append(sample)
        histograms: list[tuple[list[float], list[int]]] = []
        for group in series.values():
            group.sort(key=lambda sample: sample.timestamp)
            if group[-1].temporality == "cumulative" and group[-1].bucket_counts:
                histograms.append((group[-1].bucket_bounds or [], group[-1].bucket_counts or []))
            else:
                for sample in group:
                    if sample.bucket_counts:
                        histograms.append((sample.bucket_bounds or [], sample.bucket_counts or []))
        bounds, counts, approximate = merge_histograms(histograms)
        return bounds, counts, approximate

    @staticmethod
    def _counter_rate(samples: list[MetricSample], window: float) -> float | None:
        if not samples:
            return None
        if all(sample.temporality == "cumulative" for sample in samples):
            series: dict[tuple, list[MetricSample]] = {}
            for sample in samples:
                series.setdefault((sample.service, sample.attr_hash), []).append(sample)
            total = 0.0
            for group in series.values():
                ordered = [sample.value or 0 for sample in sorted(group, key=lambda item: item.timestamp)]
                if len(ordered) == 1:
                    total += max(0.0, ordered[0])
                elif ordered[-1] >= ordered[0]:
                    total += ordered[-1] - ordered[0]
                else:
                    total += ordered[-1]
            return total / window
        values = [sample.value or 0 for sample in samples]
        return sum(values) / window

    def _log_stats(self, project_id: str, start: datetime, end: datetime) -> dict:
        base = [LogEntry.project_id == project_id, LogEntry.timestamp >= start, LogEntry.timestamp <= end]
        total = int(self.db.scalar(select(func.count()).select_from(LogEntry).where(*base)) or 0)
        error = int(
            self.db.scalar(
                select(func.count()).select_from(LogEntry).where(*base, LogEntry.severity_number >= 17, LogEntry.severity_number < 21)
            )
            or 0
        )
        fatal = int(
            self.db.scalar(select(func.count()).select_from(LogEntry).where(*base, LogEntry.severity_number >= 21))
            or 0
        )
        return {
            "total": total,
            "error": error,
            "fatal": fatal,
            "by_severity": self._severity(project_id, start, end),
            "timeseries": self._count_series(project_id, start, end, minimum_severity=None),
        }

    def _severity(self, project_id: str, start: datetime, end: datetime) -> dict[str, int]:
        rows = self.db.execute(
            select(LogEntry.severity_text, func.count())
            .where(LogEntry.project_id == project_id, LogEntry.timestamp >= start, LogEntry.timestamp <= end)
            .group_by(LogEntry.severity_text)
        ).all()
        return {str(name): int(count) for name, count in rows}

    def _count_series(self, project_id: str, start: datetime, end: datetime, minimum_severity: int | None) -> list[dict]:
        seconds = bucket_seconds(start, end)
        label = bucket_label(LogEntry.timestamp, seconds)
        stmt = select(label, func.count()).where(
            LogEntry.project_id == project_id,
            LogEntry.timestamp >= start,
            LogEntry.timestamp <= end,
        )
        if minimum_severity is not None:
            stmt = stmt.where(LogEntry.severity_number >= minimum_severity)
        rows = self.db.execute(stmt.group_by(label).order_by(label.asc())).all()
        return [{"timestamp": ts, "count": int(count)} for ts, count in rows if ts]

    def _grouped(self, project_id: str, start: datetime, end: datetime, column, minimum_severity: int | None) -> list[dict]:
        stmt = select(column, func.count()).where(
            LogEntry.project_id == project_id,
            LogEntry.timestamp >= start,
            LogEntry.timestamp <= end,
        )
        if minimum_severity is not None:
            stmt = stmt.where(LogEntry.severity_number >= minimum_severity)
        rows = self.db.execute(stmt.group_by(column).order_by(func.count().desc()).limit(10)).all()
        return [{"name": name, "count": int(count)} for name, count in rows]

    def _top_messages(self, project_id: str, start: datetime, end: datetime) -> list[dict]:
        rows = self.db.execute(
            select(LogEntry.message, func.count())
            .where(
                LogEntry.project_id == project_id,
                LogEntry.timestamp >= start,
                LogEntry.timestamp <= end,
                LogEntry.severity_number >= 17,
            )
            .group_by(LogEntry.message)
            .order_by(func.count().desc())
            .limit(10)
        ).all()
        return [{"message": message, "count": int(count)} for message, count in rows]

    def _alert_counts(self, project_id: str) -> dict:
        rows = self.db.execute(
            select(AlertIncident.status, func.count()).where(AlertIncident.project_id == project_id).group_by(AlertIncident.status)
        ).all()
        counts = {status: int(count) for status, count in rows}
        active = counts.get("PENDING", 0) + counts.get("FIRING", 0) + counts.get("ACKNOWLEDGED", 0)
        return {
            "active": active,
            "pending": counts.get("PENDING", 0),
            "firing": counts.get("FIRING", 0),
            "acknowledged": counts.get("ACKNOWLEDGED", 0),
            "resolved": counts.get("RESOLVED", 0),
        }

    def _recent_errors(self, project_id: str, start: datetime, end: datetime):
        rows = self.db.scalars(
            select(LogEntry)
            .where(
                LogEntry.project_id == project_id,
                LogEntry.timestamp >= start,
                LogEntry.timestamp <= end,
                LogEntry.severity_number >= 17,
            )
            .order_by(LogEntry.timestamp.desc())
            .limit(8)
        ).all()
        from app.services.ingestion import log_to_schema

        return [log_to_schema(row) for row in rows]

    def _recent_alerts(self, project_id: str) -> list[dict]:
        rows = self.db.scalars(
            select(AlertIncident)
            .where(
                AlertIncident.project_id == project_id,
                AlertIncident.status.in_(("PENDING", "FIRING", "ACKNOWLEDGED")),
            )
            .order_by(AlertIncident.last_seen.desc())
            .limit(8)
        ).all()
        return [
            {
                "id": row.id,
                "title": row.title,
                "severity": row.severity,
                "status": row.status,
                "service": row.service,
                "last_seen": row.last_seen.isoformat(),
            }
            for row in rows
        ]

    def _alert_trend(self, project_id: str, start: datetime, end: datetime) -> list[dict]:
        seconds = bucket_seconds(start, end)
        label = bucket_label(AlertIncident.first_seen, seconds)
        rows = self.db.execute(
            select(label, func.count())
            .where(
                AlertIncident.project_id == project_id,
                AlertIncident.first_seen >= start,
                AlertIncident.first_seen <= end,
            )
            .group_by(label)
            .order_by(label.asc())
        ).all()
        return [{"timestamp": ts, "count": int(count)} for ts, count in rows if ts]

    def _traffic(self, project_id: str, start: datetime, end: datetime) -> dict:
        conditions = [
            TraceSpan.project_id == project_id,
            TraceSpan.start_time >= start,
            TraceSpan.start_time <= end,
            TraceSpan.kind.in_(("server", "consumer")),
        ]
        total = int(self.db.scalar(select(func.count()).select_from(TraceSpan).where(*conditions)) or 0)
        errors = int(
            self.db.scalar(
                select(func.count()).select_from(TraceSpan).where(*conditions, TraceSpan.status_code == "error")
            )
            or 0
        )
        cap = get_settings().latency_sample_cap
        durations = [
            float(value)
            for value in self.db.scalars(
                select(TraceSpan.duration_ms).where(*conditions).order_by(TraceSpan.start_time.desc()).limit(cap)
            ).all()
            if value is not None
        ]
        window = max(1.0, (end - start).total_seconds())
        return {
            "request_count": total,
            "request_rate": total / window,
            "error_count": errors,
            "error_rate": (errors / total) if total else None,
            "p50_ms": percentile(durations, 0.50),
            "p95_ms": percentile(durations, 0.95),
            "p99_ms": percentile(durations, 0.99),
            "sample_count": len(durations),
            "latency_approximate": total > cap,
            "has_data": total > 0,
        }

    def _latency_buckets(self, project_id: str, start: datetime, end: datetime) -> list[dict]:
        cap = get_settings().latency_sample_cap
        durations = [
            float(value)
            for value in self.db.scalars(
                select(TraceSpan.duration_ms)
                .where(
                    TraceSpan.project_id == project_id,
                    TraceSpan.start_time >= start,
                    TraceSpan.start_time <= end,
                    TraceSpan.kind.in_(("server", "consumer")),
                )
                .order_by(TraceSpan.start_time.desc())
                .limit(cap)
            ).all()
            if value is not None
        ]
        edges = [10, 25, 50, 100, 250, 500, 1000, 2500]
        counts = [0 for _ in range(len(edges) + 1)]
        for duration in durations:
            placed = False
            for index, edge in enumerate(edges):
                if duration <= edge:
                    counts[index] += 1
                    placed = True
                    break
            if not placed:
                counts[-1] += 1
        labels = [f"≤{edge}ms" for edge in edges] + [f">{edges[-1]}ms"]
        return [{"bucket": label, "count": count} for label, count in zip(labels, counts, strict=True)]

    def _service_comparison(self, project_id: str, start: datetime, end: datetime) -> list[dict]:
        rows = self.db.execute(
            select(
                LogEntry.service,
                func.count(),
                func.sum(case((LogEntry.severity_number >= 17, 1), else_=0)),
            )
            .where(LogEntry.project_id == project_id, LogEntry.timestamp >= start, LogEntry.timestamp <= end)
            .group_by(LogEntry.service)
            .order_by(func.count().desc())
            .limit(12)
        ).all()
        return [
            {"service": service, "logs": int(total), "errors": int(errors or 0)}
            for service, total, errors in rows
        ]

    def _ingestion(self, project_id: str, start: datetime, end: datetime) -> dict:
        logs = int(
            self.db.scalar(
                select(func.count())
                .select_from(LogEntry)
                .where(LogEntry.project_id == project_id, LogEntry.ingested_at >= start, LogEntry.ingested_at <= end)
            )
            or 0
        )
        spans = int(
            self.db.scalar(
                select(func.count())
                .select_from(TraceSpan)
                .where(TraceSpan.project_id == project_id, TraceSpan.start_time >= start, TraceSpan.start_time <= end)
            )
            or 0
        )
        metrics = int(
            self.db.scalar(
                select(func.count())
                .select_from(MetricSample)
                .where(
                    MetricSample.project_id == project_id,
                    MetricSample.timestamp >= start,
                    MetricSample.timestamp <= end,
                )
            )
            or 0
        )
        window = max(1.0, (end - start).total_seconds())
        return {
            "logs": logs,
            "spans": spans,
            "metrics": metrics,
            "logs_per_second": logs / window,
            "events_per_second": (logs + spans + metrics) / window,
        }

    @staticmethod
    def _python_bucket(value: datetime, seconds: int) -> str:
        moment = _aware(value).astimezone(timezone.utc).replace(microsecond=0)
        epoch = int(moment.timestamp())
        floored = epoch - (epoch % seconds)
        return datetime.fromtimestamp(floored, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
