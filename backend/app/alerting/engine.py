from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.alerting.notifier import deliver_webhook, validate_webhook_url
from app.core.config import get_settings
from app.core.security import utcnow
from app.models import (
    AlertHistory,
    AlertIncident,
    AlertRule,
    EventRecord,
    LogEntry,
    MetricSample,
    NotificationChannel,
    NotificationDelivery,
    ServiceRecord,
    TraceSpan,
)
from app.schemas.alerts import AlertIn, AlertRuleIn, ChannelIn
from app.services.ingestion import bump
from app.telemetry.histogram import histogram_quantile, merge_histograms, percentile
from app.telemetry.severity import normalize_severity

logger = logging.getLogger(__name__)

OPEN_STATUSES = ("PENDING", "FIRING", "ACKNOWLEDGED")


def breached(value: float, threshold: float, comparison: str) -> bool:
    if comparison == "gt":
        return value > threshold
    if comparison == "gte":
        return value >= threshold
    if comparison == "lt":
        return value < threshold
    if comparison == "lte":
        return value <= threshold
    raise ValueError(f"unsupported comparison {comparison}")


def rule_fingerprint(rule: AlertRule) -> str:
    raw = "|".join(
        [
            rule.id,
            rule.condition_type,
            rule.service or "*",
            rule.environment or "*",
            rule.metric_name or "",
            rule.event_name or "",
            rule.log_severity or "",
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def external_fingerprint(alert: AlertIn) -> str:
    if alert.fingerprint:
        return alert.fingerprint[:128]
    raw = f"{alert.title}|{alert.service or ''}|{alert.environment or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class AlertService:
    def __init__(self, db: Session):
        self.db = db

    def submit_external(self, project_id: str, alert: AlertIn, actor: str = "api") -> AlertIncident:
        fingerprint = external_fingerprint(alert)
        return self._open_or_update(
            project_id=project_id,
            rule=None,
            fingerprint=fingerprint,
            title=alert.title,
            message=alert.message,
            severity=alert.severity,
            service=alert.service,
            environment=alert.environment,
            value=None,
            threshold=None,
            attributes=alert.attributes,
            actor=actor,
            cooldown_seconds=0,
        )

    def create_rule(self, project_id: str, payload: AlertRuleIn) -> AlertRule:
        rule = AlertRule(project_id=project_id, **payload.model_dump())
        self.db.add(rule)
        self.db.flush()
        return rule

    def update_rule(self, project_id: str, rule_id: str, payload: AlertRuleIn) -> AlertRule:
        rule = self._rule(project_id, rule_id)
        for key, value in payload.model_dump().items():
            setattr(rule, key, value)
        rule.updated_at = utcnow()
        return rule

    def delete_rule(self, project_id: str, rule_id: str) -> None:
        rule = self._rule(project_id, rule_id)
        self.db.delete(rule)

    def list_rules(self, project_id: str) -> list[AlertRule]:
        return list(
            self.db.scalars(
                select(AlertRule).where(AlertRule.project_id == project_id).order_by(AlertRule.created_at.desc())
            ).all()
        )

    def get_rule(self, project_id: str, rule_id: str) -> AlertRule:
        return self._rule(project_id, rule_id)

    def list_alerts(
        self,
        project_id: str,
        *,
        status: str | None,
        severity: str | None,
        service: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AlertIncident], int]:
        stmt = select(AlertIncident).where(AlertIncident.project_id == project_id)
        count_stmt = select(func.count()).select_from(AlertIncident).where(AlertIncident.project_id == project_id)
        if status:
            stmt = stmt.where(AlertIncident.status == status.upper())
            count_stmt = count_stmt.where(AlertIncident.status == status.upper())
        if severity:
            stmt = stmt.where(AlertIncident.severity == severity.upper())
            count_stmt = count_stmt.where(AlertIncident.severity == severity.upper())
        if service:
            stmt = stmt.where(AlertIncident.service == service)
            count_stmt = count_stmt.where(AlertIncident.service == service)
        total = int(self.db.scalar(count_stmt) or 0)
        rows = list(
            self.db.scalars(
                stmt.order_by(AlertIncident.last_seen.desc()).offset((page - 1) * page_size).limit(page_size)
            ).all()
        )
        return rows, total

    def get_alert(self, project_id: str, alert_id: str) -> AlertIncident:
        row = self.db.scalar(
            select(AlertIncident).where(AlertIncident.project_id == project_id, AlertIncident.id == alert_id)
        )
        if row is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Alert not found")
        return row

    def history(self, alert_id: str) -> list[AlertHistory]:
        return list(
            self.db.scalars(
                select(AlertHistory).where(AlertHistory.alert_id == alert_id).order_by(AlertHistory.created_at.asc())
            ).all()
        )

    def acknowledge(self, project_id: str, alert_id: str, actor: str) -> AlertIncident:
        alert = self.get_alert(project_id, alert_id)
        if alert.status == "ACKNOWLEDGED":
            return alert
        if alert.status not in {"PENDING", "FIRING"}:
            from fastapi import HTTPException

            raise HTTPException(status_code=409, detail=f"Cannot acknowledge an alert in status {alert.status}")
        self._transition(alert, "ACKNOWLEDGED", "Acknowledged", actor)
        return alert

    def resolve(self, project_id: str, alert_id: str, actor: str) -> AlertIncident:
        alert = self.get_alert(project_id, alert_id)
        if alert.status == "RESOLVED":
            return alert
        if alert.status not in OPEN_STATUSES:
            from fastapi import HTTPException

            raise HTTPException(status_code=409, detail=f"Cannot resolve an alert in status {alert.status}")
        self._transition(alert, "RESOLVED", "Resolved", actor)
        return alert

    def create_channel(self, project_id: str, payload: ChannelIn) -> NotificationChannel:
        url = validate_webhook_url(payload.url)
        channel = NotificationChannel(
            project_id=project_id,
            name=payload.name,
            channel_type=payload.channel_type,
            config={"url": url, "headers": payload.headers},
            enabled=payload.enabled,
        )
        self.db.add(channel)
        self.db.flush()
        return channel

    def list_channels(self, project_id: str) -> list[NotificationChannel]:
        return list(
            self.db.scalars(
                select(NotificationChannel)
                .where(NotificationChannel.project_id == project_id)
                .order_by(NotificationChannel.created_at.desc())
            ).all()
        )

    def delete_channel(self, project_id: str, channel_id: str) -> None:
        row = self.db.scalar(
            select(NotificationChannel).where(
                NotificationChannel.project_id == project_id,
                NotificationChannel.id == channel_id,
            )
        )
        if row is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Notification channel not found")
        self.db.delete(row)

    def evaluate_all(self) -> int:
        rules = list(self.db.scalars(select(AlertRule).where(AlertRule.enabled.is_(True))).all())
        fired = 0
        for rule in rules:
            try:
                with self.db.begin_nested():
                    if self.evaluate_rule(rule):
                        fired += 1
            except Exception:
                logger.exception("alert rule evaluation failed", extra={"rule_id": rule.id})
        bump(self.db, "alert_evaluations", 1)
        return fired

    def evaluate_rule(self, rule: AlertRule) -> bool:
        outcome = self._measure(rule)
        fingerprint = rule_fingerprint(rule)
        open_incident = self._open_incident(rule.project_id, fingerprint)
        if outcome is None:
            if open_incident and rule.auto_resolve:
                self._transition(open_incident, "RESOLVED", "Condition cleared", "rule-engine")
            return False
        value, threshold, comparison = outcome
        if breached(value, threshold, comparison):
            self._open_or_update(
                project_id=rule.project_id,
                rule=rule,
                fingerprint=fingerprint,
                title=rule.name,
                message=self._message(rule, value, threshold),
                severity=rule.severity,
                service=rule.service,
                environment=rule.environment,
                value=value,
                threshold=threshold,
                attributes={"labels": rule.labels or {}},
                actor="rule-engine",
                cooldown_seconds=rule.cooldown_seconds,
            )
            return True
        if open_incident and rule.auto_resolve:
            self._transition(open_incident, "RESOLVED", "Condition cleared", "rule-engine")
        return False

    def deliver_pending(self) -> int:
        deliveries = list(
            self.db.scalars(
                select(NotificationDelivery).where(NotificationDelivery.status == "pending").limit(50)
            ).all()
        )
        settings = get_settings()
        sent = 0
        for delivery in deliveries:
            channel = self.db.get(NotificationChannel, delivery.channel_id) if delivery.channel_id else None
            if channel is None or not channel.enabled:
                delivery.status = "failed"
                delivery.error = "notification channel is missing or disabled"
                delivery.attempt = 1
                continue
            url = str((channel.config or {}).get("url") or "")
            headers = dict((channel.config or {}).get("headers") or {})
            status, code, error, attempts = deliver_webhook(
                url,
                delivery.payload or {},
                headers,
                settings.webhook_timeout_seconds,
            )
            delivery.status = status
            delivery.response_code = code
            delivery.error = error
            delivery.attempt = attempts
            if status == "success":
                sent += 1
                bump(self.db, "notifications_sent", 1)
            else:
                bump(self.db, "notifications_failed", 1)
        pending_alerts = list(
            self.db.scalars(select(AlertIncident).where(AlertIncident.status == "PENDING")).all()
        )
        for alert in pending_alerts:
            remaining = self.db.scalar(
                select(func.count())
                .select_from(NotificationDelivery)
                .where(NotificationDelivery.alert_id == alert.id, NotificationDelivery.status == "pending")
            )
            if not remaining:
                self._transition(alert, "FIRING", "Notification attempts finished", "rule-engine")
        return sent

    def _measure(self, rule: AlertRule) -> tuple[float, float, str] | None:
        end = utcnow()
        start = end - timedelta(seconds=rule.window_seconds)
        if rule.condition_type == "error_count":
            return float(self._log_count(rule, start, end, minimum=17)), rule.threshold, rule.comparison
        if rule.condition_type == "log_severity":
            text, number = normalize_severity(rule.log_severity, None)
            return float(self._log_count(rule, start, end, exact=text or None, exact_number=number)), rule.threshold, rule.comparison
        if rule.condition_type == "error_rate":
            total = self._log_count(rule, start, end)
            if total == 0:
                return None
            errors = self._log_count(rule, start, end, minimum=17)
            return (errors / total) * 100, rule.threshold, rule.comparison
        if rule.condition_type == "event_match":
            return float(self._event_count(rule, start, end)), rule.threshold, rule.comparison
        if rule.condition_type == "service_silence":
            age = self._silence_seconds(rule)
            if age is None:
                return None
            return age, float(rule.window_seconds), "gt"
        if rule.condition_type == "p95_latency":
            value = self._p95(rule, start, end)
            if value is None:
                return None
            return value, rule.threshold, rule.comparison
        if rule.condition_type == "metric_threshold":
            value = self._metric_value(rule, start, end)
            if value is None:
                return None
            return value, rule.threshold, rule.comparison
        logger.warning("unknown alert condition", extra={"condition": rule.condition_type})
        return None

    def _log_count(
        self,
        rule: AlertRule,
        start,
        end,
        minimum: int | None = None,
        exact: str | None = None,
        exact_number: int | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(LogEntry).where(
            LogEntry.project_id == rule.project_id,
            LogEntry.timestamp >= start,
            LogEntry.timestamp <= end,
        )
        if rule.service:
            stmt = stmt.where(LogEntry.service == rule.service)
        if rule.environment:
            stmt = stmt.where(LogEntry.environment == rule.environment)
        if exact:
            stmt = stmt.where(LogEntry.severity_text == exact)
        elif minimum is not None:
            stmt = stmt.where(LogEntry.severity_number >= minimum)
        elif exact_number is not None:
            stmt = stmt.where(LogEntry.severity_number == exact_number)
        return int(self.db.scalar(stmt) or 0)

    def _event_count(self, rule: AlertRule, start, end) -> int:
        stmt = select(func.count()).select_from(EventRecord).where(
            EventRecord.project_id == rule.project_id,
            EventRecord.timestamp >= start,
            EventRecord.timestamp <= end,
            EventRecord.name == rule.event_name,
        )
        if rule.service:
            stmt = stmt.where(EventRecord.service == rule.service)
        if rule.environment:
            stmt = stmt.where(EventRecord.environment == rule.environment)
        return int(self.db.scalar(stmt) or 0)

    def _silence_seconds(self, rule: AlertRule) -> float | None:
        stmt = select(func.max(ServiceRecord.last_seen)).where(
            ServiceRecord.project_id == rule.project_id,
            ServiceRecord.name == rule.service,
        )
        if rule.environment:
            stmt = stmt.where(ServiceRecord.environment == rule.environment)
        last_seen = self.db.scalar(stmt)
        if last_seen is None:
            return None
        return (utcnow() - last_seen).total_seconds()

    def _p95(self, rule: AlertRule, start, end) -> float | None:
        if rule.metric_name:
            return self._metric_value(rule, start, end)
        stmt = select(TraceSpan.duration_ms).where(
            TraceSpan.project_id == rule.project_id,
            TraceSpan.start_time >= start,
            TraceSpan.start_time <= end,
            TraceSpan.kind.in_(("server", "consumer")),
        )
        if rule.service:
            stmt = stmt.where(TraceSpan.service == rule.service)
        if rule.environment:
            stmt = stmt.where(TraceSpan.environment == rule.environment)
        values = [float(value) for value in self.db.scalars(stmt.limit(get_settings().latency_sample_cap)).all()]
        return percentile(values, 0.95)

    def _metric_value(self, rule: AlertRule, start, end) -> float | None:
        stmt = (
            select(MetricSample)
            .where(
                MetricSample.project_id == rule.project_id,
                MetricSample.name == rule.metric_name,
                MetricSample.timestamp >= start,
                MetricSample.timestamp <= end,
            )
            .order_by(MetricSample.timestamp.asc())
            .limit(5000)
        )
        if rule.service:
            stmt = stmt.where(MetricSample.service == rule.service)
        if rule.environment:
            stmt = stmt.where(MetricSample.environment == rule.environment)
        samples = list(self.db.scalars(stmt).all())
        if not samples:
            return None
        if samples[-1].metric_type in {"histogram", "exponential_histogram"}:
            histograms = [
                (sample.bucket_bounds or [], sample.bucket_counts or [])
                for sample in samples
                if sample.bucket_counts
            ]
            bounds, counts, _approximate = merge_histograms(histograms)
            if not counts:
                return None
            return histogram_quantile(0.95, bounds, counts)
        latest = samples[-1]
        return float(latest.value) if latest.value is not None else None

    def _open_or_update(
        self,
        *,
        project_id: str,
        rule: AlertRule | None,
        fingerprint: str,
        title: str,
        message: str,
        severity: str,
        service: str | None,
        environment: str | None,
        value: float | None,
        threshold: float | None,
        attributes: dict,
        actor: str,
        cooldown_seconds: int,
    ) -> AlertIncident:
        existing = self._open_incident(project_id, fingerprint)
        now = utcnow()
        if existing is not None:
            existing.last_seen = now
            existing.trigger_value = value
            existing.message = message
            if threshold is not None:
                existing.threshold = threshold
            return existing
        if cooldown_seconds > 0:
            previous = self.db.scalar(
                select(AlertIncident)
                .where(AlertIncident.project_id == project_id, AlertIncident.fingerprint == fingerprint)
                .order_by(AlertIncident.resolved_at.desc())
            )
            if (
                previous is not None
                and previous.status == "RESOLVED"
                and previous.resolved_at is not None
                and (now - previous.resolved_at).total_seconds() < cooldown_seconds
            ):
                return previous
        incident = AlertIncident(
            project_id=project_id,
            rule_id=rule.id if rule else None,
            fingerprint=fingerprint,
            title=title,
            message=message,
            severity=severity,
            status="PENDING",
            service=service,
            environment=environment,
            trigger_value=value,
            threshold=threshold,
            attributes=attributes,
            first_seen=now,
            last_seen=now,
        )
        try:
            with self.db.begin_nested():
                self.db.add(incident)
                self.db.flush()
        except IntegrityError:
            raced = self._open_incident(project_id, fingerprint)
            if raced is None:
                raise
            raced.last_seen = now
            raced.trigger_value = value
            return raced
        self.db.add(
            AlertHistory(
                alert_id=incident.id,
                from_status=None,
                to_status="PENDING",
                message="Incident opened",
                actor=actor,
            )
        )
        channels = list(
            self.db.scalars(
                select(NotificationChannel).where(
                    NotificationChannel.project_id == project_id,
                    NotificationChannel.enabled.is_(True),
                )
            ).all()
        )
        payload = {
            "alert_id": incident.id,
            "title": title,
            "message": message,
            "severity": severity,
            "status": "FIRING",
            "service": service,
            "environment": environment,
            "fingerprint": fingerprint,
            "trigger_value": value,
            "threshold": threshold,
            "first_seen": now.isoformat(),
            "last_seen": now.isoformat(),
        }
        if channels:
            for channel in channels:
                self.db.add(
                    NotificationDelivery(
                        alert_id=incident.id,
                        channel_id=channel.id,
                        status="pending",
                        payload=payload,
                    )
                )
        else:
            self._transition(incident, "FIRING", "No notification channels configured", actor)
        bump(self.db, "alerts_opened", 1)
        return incident

    def _open_incident(self, project_id: str, fingerprint: str) -> AlertIncident | None:
        return self.db.scalar(
            select(AlertIncident).where(
                AlertIncident.project_id == project_id,
                AlertIncident.fingerprint == fingerprint,
                AlertIncident.status.in_(OPEN_STATUSES),
            )
        )

    def _transition(self, alert: AlertIncident, status: str, message: str, actor: str | None) -> None:
        if alert.status == status:
            return
        previous = alert.status
        alert.status = status
        now = utcnow()
        if status == "ACKNOWLEDGED":
            alert.acknowledged_at = now
        if status == "RESOLVED":
            alert.resolved_at = now
        alert.last_seen = now
        self.db.add(
            AlertHistory(
                alert_id=alert.id,
                from_status=previous,
                to_status=status,
                message=message,
                actor=actor,
            )
        )

    def _rule(self, project_id: str, rule_id: str) -> AlertRule:
        rule = self.db.scalar(select(AlertRule).where(AlertRule.project_id == project_id, AlertRule.id == rule_id))
        if rule is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Alert rule not found")
        return rule

    @staticmethod
    def _message(rule: AlertRule, value: float, threshold: float) -> str:
        return (
            f"{rule.name}: {rule.condition_type} is {value:.4g} "
            f"compared with threshold {threshold:.4g} over {rule.window_seconds}s"
        )
