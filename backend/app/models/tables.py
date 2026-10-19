from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.security import utcnow
from app.db.base import Base, UTCDateTime, new_id


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(32), default="admin")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    key_prefix: Mapped[str] = mapped_column(String(32))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class LogEntry(Base):
    __tablename__ = "logs"
    __table_args__ = (
        Index("ix_logs_project_ts", "project_id", "timestamp"),
        Index("ix_logs_project_sev_ts", "project_id", "severity_number", "timestamp"),
        Index("ix_logs_project_service_ts", "project_id", "service", "timestamp"),
        Index("ix_logs_project_trace", "project_id", "trace_id"),
        UniqueConstraint("project_id", "event_id", name="uq_logs_project_event"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    ingested_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    severity_text: Mapped[str] = mapped_column(String(16), index=True)
    severity_number: Mapped[int] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text)
    service: Mapped[str] = mapped_column(String(200), default="unknown")
    environment: Mapped[str] = mapped_column(String(100), default="production")
    logger_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    span_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(200), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    exception_type: Mapped[str | None] = mapped_column(String(300), nullable=True)
    exception_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class TraceSummary(Base):
    __tablename__ = "trace_summaries"
    __table_args__ = (
        UniqueConstraint("project_id", "trace_id", name="uq_trace_project"),
        Index("ix_traces_project_start", "project_id", "start_time"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    trace_id: Mapped[str] = mapped_column(String(64))
    root_span_name: Mapped[str] = mapped_column(String(500), default="")
    service: Mapped[str] = mapped_column(String(200), default="unknown")
    environment: Mapped[str | None] = mapped_column(String(100), nullable=True)
    start_time: Mapped[datetime] = mapped_column(UTCDateTime)
    end_time: Mapped[datetime] = mapped_column(UTCDateTime)
    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    span_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="ok")


class TraceSpan(Base):
    __tablename__ = "spans"
    __table_args__ = (
        UniqueConstraint("project_id", "trace_id", "span_id", name="uq_span_identity"),
        Index("ix_spans_trace", "project_id", "trace_id"),
        Index("ix_spans_project_start", "project_id", "start_time"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    trace_id: Mapped[str] = mapped_column(String(64))
    span_id: Mapped[str] = mapped_column(String(32))
    parent_span_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(32), default="internal")
    start_time: Mapped[datetime] = mapped_column(UTCDateTime)
    end_time: Mapped[datetime] = mapped_column(UTCDateTime)
    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    status_code: Mapped[str] = mapped_column(String(16), default="unset")
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    service: Mapped[str] = mapped_column(String(200), default="unknown")
    environment: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    events: Mapped[list] = mapped_column(JSON, default=list)
    links: Mapped[list] = mapped_column(JSON, default=list)
    resource_attributes: Mapped[dict] = mapped_column(JSON, default=dict)


class MetricSample(Base):
    __tablename__ = "metric_samples"
    __table_args__ = (
        Index("ix_metrics_project_name_ts", "project_id", "name", "timestamp"),
        Index("ix_metrics_series", "project_id", "name", "service", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metric_type: Mapped[str] = mapped_column(String(32))
    temporality: Mapped[str] = mapped_column(String(16), default="delta")
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    service: Mapped[str] = mapped_column(String(200), default="unknown")
    environment: Mapped[str] = mapped_column(String(100), default="production")
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sum: Mapped[float | None] = mapped_column(Float, nullable=True)
    min: Mapped[float | None] = mapped_column(Float, nullable=True)
    max: Mapped[float | None] = mapped_column(Float, nullable=True)
    bucket_bounds: Mapped[list | None] = mapped_column(JSON, nullable=True)
    bucket_counts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    attr_hash: Mapped[str] = mapped_column(String(64), default="")
    is_monotonic: Mapped[bool] = mapped_column(Boolean, default=True)


class EventRecord(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_project_ts", "project_id", "timestamp"),
        Index("ix_events_project_name", "project_id", "name", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime)
    name: Mapped[str] = mapped_column(String(200))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    service: Mapped[str] = mapped_column(String(200), default="unknown")
    environment: Mapped[str] = mapped_column(String(100), default="production")
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)


class ServiceRecord(Base):
    __tablename__ = "services"
    __table_args__ = (UniqueConstraint("project_id", "name", "environment", name="uq_service_identity"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    environment: Mapped[str] = mapped_column(String(100), default="production")
    version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition_type: Mapped[str] = mapped_column(String(64))
    threshold: Mapped[float] = mapped_column(Float)
    comparison: Mapped[str] = mapped_column(String(8), default="gt")
    window_seconds: Mapped[int] = mapped_column(Integer, default=300)
    severity: Mapped[str] = mapped_column(String(16), default="HIGH")
    service: Mapped[str | None] = mapped_column(String(200), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metric_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    event_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    log_severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    labels: Mapped[dict] = mapped_column(JSON, default=dict)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300)
    auto_resolve: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class AlertIncident(Base):
    __tablename__ = "alert_incidents"
    __table_args__ = (
        Index("ix_alerts_project_status", "project_id", "status", "last_seen"),
        Index(
            "uq_open_alert_fingerprint",
            "project_id",
            "fingerprint",
            unique=True,
            sqlite_where=text("status != 'RESOLVED'"),
            postgresql_where=text("status != 'RESOLVED'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[str | None] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    fingerprint: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    service: Mapped[str | None] = mapped_column(String(200), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(100), nullable=True)
    trigger_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    first_seen: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class AlertHistory(Base):
    __tablename__ = "alert_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alert_incidents.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    channel_type: Mapped[str] = mapped_column(String(32), default="webhook")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alert_incidents.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[str | None] = mapped_column(
        ForeignKey("notification_channels.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pending")
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("project_id", "key", name="uq_idempotency"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(200))
    body_hash: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int] = mapped_column(Integer)
    response_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PlatformCounter(Base):
    __tablename__ = "platform_counters"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)
