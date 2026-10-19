from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import utcnow
from app.models import (
    AlertHistory,
    AlertIncident,
    EventRecord,
    IdempotencyRecord,
    LogEntry,
    MetricSample,
    NotificationDelivery,
    ServiceRecord,
    TraceSpan,
    TraceSummary,
)
from app.services.ingestion import bump

logger = logging.getLogger(__name__)


def _purge(db: Session, model, column, cutoff, extra=None, batch_size: int = 1000) -> int:
    removed = 0
    while True:
        stmt = select(model.id).where(column < cutoff)
        if extra is not None:
            stmt = stmt.where(extra)
        ids = list(db.scalars(stmt.limit(batch_size)).all())
        if not ids:
            break
        db.execute(delete(model).where(model.id.in_(ids)))
        db.commit()
        removed += len(ids)
        if len(ids) < batch_size:
            break
    return removed


def run_retention(db: Session) -> dict[str, int]:
    settings = get_settings()
    cutoff = utcnow() - timedelta(days=settings.retention_days)
    idempotency_cutoff = utcnow() - timedelta(hours=settings.idempotency_ttl_hours)
    # Delete children before parents. Each batch commits so SQLite write
    # transactions stay short.
    deleted = {
        "logs": _purge(db, LogEntry, LogEntry.timestamp, cutoff),
        "spans": _purge(db, TraceSpan, TraceSpan.start_time, cutoff),
        "traces": _purge(db, TraceSummary, TraceSummary.end_time, cutoff),
        "metrics": _purge(db, MetricSample, MetricSample.timestamp, cutoff),
        "events": _purge(db, EventRecord, EventRecord.timestamp, cutoff),
        "services": _purge(db, ServiceRecord, ServiceRecord.last_seen, cutoff),
        "idempotency": _purge(db, IdempotencyRecord, IdempotencyRecord.created_at, idempotency_cutoff),
    }
    resolved_ids = list(
        db.scalars(
            select(AlertIncident.id).where(
                AlertIncident.status == "RESOLVED",
                AlertIncident.resolved_at.is_not(None),
                AlertIncident.resolved_at < cutoff,
            ).limit(1000)
        ).all()
    )
    if resolved_ids:
        db.execute(delete(NotificationDelivery).where(NotificationDelivery.alert_id.in_(resolved_ids)))
        db.execute(delete(AlertHistory).where(AlertHistory.alert_id.in_(resolved_ids)))
        db.execute(delete(AlertIncident).where(AlertIncident.id.in_(resolved_ids)))
        db.commit()
    deleted["resolved_alerts"] = len(resolved_ids)
    total = sum(deleted.values())
    if total:
        bump(db, "retention_deleted", total)
        db.commit()
        logger.info("retention cleanup removed rows", extra={"deleted": deleted})
    return deleted
