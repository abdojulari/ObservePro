"""ORM models. Importing this package registers every table on Base.metadata."""

from app.models.tables import (
    AlertHistory,
    AlertIncident,
    AlertRule,
    ApiKey,
    EventRecord,
    IdempotencyRecord,
    LogEntry,
    MetricSample,
    NotificationChannel,
    NotificationDelivery,
    PlatformCounter,
    Project,
    ServiceRecord,
    TraceSpan,
    TraceSummary,
    User,
)

__all__ = [
    "AlertHistory",
    "AlertIncident",
    "AlertRule",
    "ApiKey",
    "EventRecord",
    "IdempotencyRecord",
    "LogEntry",
    "MetricSample",
    "NotificationChannel",
    "NotificationDelivery",
    "PlatformCounter",
    "Project",
    "ServiceRecord",
    "TraceSpan",
    "TraceSummary",
    "User",
]
