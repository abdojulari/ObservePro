from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.redaction import json_size
from app.telemetry.severity import ALERT_SEVERITIES, SEVERITY_ORDER

AlertSeverity = Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL", "EMERGENCY"]
MetricType = Literal["counter", "gauge", "histogram", "exponential_histogram", "summary"]
Temporality = Literal["delta", "cumulative"]


class ExceptionIn(BaseModel):
    type: str | None = Field(default=None, max_length=300)
    message: str | None = Field(default=None, max_length=8000)
    stacktrace: str | None = Field(default=None, max_length=65536)


class ExceptionOut(BaseModel):
    type: str | None = None
    message: str | None = None
    stacktrace: str | None = None


class LogIn(BaseModel):
    timestamp: datetime | None = None
    severity: str | None = None
    severity_number: int | None = Field(default=None, ge=1, le=24)
    message: str = Field(min_length=1, max_length=16384)
    service: str = Field(default="unknown", max_length=200)
    environment: str = Field(default="production", max_length=100)
    logger: str | None = Field(default=None, max_length=200)
    trace_id: str | None = Field(default=None, max_length=128)
    span_id: str | None = Field(default=None, max_length=64)
    request_id: str | None = Field(default=None, max_length=128)
    hostname: str | None = Field(default=None, max_length=200)
    version: str | None = Field(default=None, max_length=100)
    source_file: str | None = Field(default=None, max_length=500)
    source_line: int | None = Field(default=None, ge=0, le=10_000_000)
    attributes: dict[str, Any] = Field(default_factory=dict)
    exception: ExceptionIn | None = None
    event_id: str | None = Field(default=None, max_length=128)
    project_id: str | None = Field(
        default=None,
        description="Ignored. The project is taken from the API key.",
    )

    @field_validator("severity")
    @classmethod
    def _severity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        key = value.strip().upper()
        aliases = {"WARNING": "WARN", "CRITICAL": "FATAL"}
        key = aliases.get(key, key)
        if key not in SEVERITY_ORDER:
            raise ValueError(f"severity must be one of {', '.join(SEVERITY_ORDER)}")
        return key

    @model_validator(mode="after")
    def _limits(self) -> LogIn:
        if json_size(self.attributes) > 65536:
            raise ValueError("attributes exceed 64KB")
        return self


class LogBatchIn(BaseModel):
    logs: list[LogIn] = Field(min_length=1, max_length=500)


class LogOut(BaseModel):
    id: str
    project_id: str
    timestamp: datetime
    ingested_at: datetime
    severity: str
    severity_number: int
    message: str
    service: str
    environment: str
    logger: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    request_id: str | None = None
    hostname: str | None = None
    version: str | None = None
    source_file: str | None = None
    source_line: int | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    exception: ExceptionOut | None = None
    event_id: str | None = None


class EventIn(BaseModel):
    timestamp: datetime | None = None
    name: str = Field(min_length=1, max_length=200)
    message: str | None = Field(default=None, max_length=8000)
    service: str = Field(default="unknown", max_length=200)
    environment: str = Field(default="production", max_length=100)
    attributes: dict[str, Any] = Field(default_factory=dict)
    project_id: str | None = None

    @model_validator(mode="after")
    def _limits(self) -> EventIn:
        if json_size(self.attributes) > 65536:
            raise ValueError("attributes exceed 64KB")
        return self


class EventBatchIn(BaseModel):
    events: list[EventIn] = Field(min_length=1, max_length=500)


class EventOut(BaseModel):
    id: str
    project_id: str
    timestamp: datetime
    name: str
    message: str | None = None
    service: str
    environment: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class MetricIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    type: MetricType = "gauge"
    timestamp: datetime | None = None
    value: float | None = None
    service: str = Field(default="unknown", max_length=200)
    environment: str = Field(default="production", max_length=100)
    unit: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=2000)
    temporality: Temporality = "delta"
    count: int | None = Field(default=None, ge=0)
    sum: float | None = None
    min: float | None = None
    max: float | None = None
    bucket_bounds: list[float] | None = None
    bucket_counts: list[int] | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    is_monotonic: bool = True
    project_id: str | None = None

    @model_validator(mode="after")
    def _histogram(self) -> MetricIn:
        if json_size(self.attributes) > 65536:
            raise ValueError("attributes exceed 64KB")
        if self.type in {"histogram", "exponential_histogram"}:
            if self.bucket_bounds is not None and self.bucket_counts is not None:
                if len(self.bucket_counts) != len(self.bucket_bounds) + 1:
                    raise ValueError("bucket_counts must be one longer than bucket_bounds (include the +Inf bucket)")
            elif self.value is None and self.count is None and self.sum is None:
                raise ValueError("histogram metrics require buckets or a value")
        elif self.value is None and self.sum is None:
            raise ValueError("value is required")
        return self


class MetricBatchIn(BaseModel):
    metrics: list[MetricIn] = Field(min_length=1, max_length=500)


class MetricSampleOut(BaseModel):
    id: str
    name: str
    type: str
    temporality: str
    timestamp: datetime
    service: str
    environment: str
    value: float | None = None
    count: int | None = None
    sum: float | None = None
    min: float | None = None
    max: float | None = None
    unit: str | None = None
    bucket_bounds: list[float] | None = None
    bucket_counts: list[int] | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class MetricNameOut(BaseModel):
    name: str
    type: str
    unit: str | None = None
    description: str | None = None


class TimeseriesPoint(BaseModel):
    timestamp: datetime
    value: float | None = None
    count: int | None = None
    sum: float | None = None
    avg: float | None = None
    p50: float | None = None
    p95: float | None = None
    p99: float | None = None


class TimeseriesOut(BaseModel):
    name: str
    type: str
    service: str | None = None
    points: list[TimeseriesPoint]
    approximate: bool = False


class MetricSummaryOut(BaseModel):
    name: str
    type: str
    count: int
    sum: float | None = None
    min: float | None = None
    max: float | None = None
    avg: float | None = None
    rate: float | None = None
    p50: float | None = None
    p95: float | None = None
    p99: float | None = None
    approximate: bool = False
    sample_count: int = 0


class SpanOut(BaseModel):
    id: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    name: str
    kind: str
    start_time: datetime
    end_time: datetime
    duration_ms: float
    status_code: str
    status_message: str | None = None
    service: str
    environment: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[Any] = Field(default_factory=list)
    links: list[Any] = Field(default_factory=list)
    resource_attributes: dict[str, Any] = Field(default_factory=dict)


class TraceOut(BaseModel):
    trace_id: str
    root_span_name: str
    service: str
    environment: str | None = None
    start_time: datetime
    end_time: datetime
    duration_ms: float
    span_count: int
    error_count: int
    status: str


class TraceDetail(TraceOut):
    spans: list[SpanOut]
    logs: list[LogOut]


class ServiceOut(BaseModel):
    name: str
    environment: str
    version: str | None = None
    first_seen: datetime
    last_seen: datetime
    health: str
    log_count: int = 0
    error_count: int = 0
    span_count: int = 0


def dumps_model(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"))
