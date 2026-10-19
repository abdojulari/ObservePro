from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.alerting.engine import AlertService
from app.alerting.notifier import WebhookError
from app.api.dependencies import DbSession, IngestProjectId, ProjectId
from app.schemas.alerts import (
    AlertHistoryOut,
    AlertIn,
    AlertOut,
    AlertRuleIn,
    AlertRuleOut,
    ChannelIn,
    ChannelOut,
)
from app.schemas.common import Page

router = APIRouter(prefix="/api/v1", tags=["alerts"])


def _alert(row, history: list | None = None) -> AlertOut:
    return AlertOut(
        id=row.id,
        project_id=row.project_id,
        rule_id=row.rule_id,
        fingerprint=row.fingerprint,
        title=row.title,
        message=row.message,
        severity=row.severity,
        status=row.status,
        service=row.service,
        environment=row.environment,
        trigger_value=row.trigger_value,
        threshold=row.threshold,
        attributes=row.attributes or {},
        first_seen=row.first_seen,
        last_seen=row.last_seen,
        acknowledged_at=row.acknowledged_at,
        resolved_at=row.resolved_at,
        history=[
            AlertHistoryOut(
                id=item.id,
                from_status=item.from_status,
                to_status=item.to_status,
                message=item.message,
                actor=item.actor,
                created_at=item.created_at,
            )
            for item in history or []
        ],
    )


def _rule(row) -> AlertRuleOut:
    return AlertRuleOut(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        description=row.description,
        condition_type=row.condition_type,
        threshold=row.threshold,
        comparison=row.comparison,
        window_seconds=row.window_seconds,
        severity=row.severity,
        service=row.service,
        environment=row.environment,
        metric_name=row.metric_name,
        event_name=row.event_name,
        log_severity=row.log_severity,
        labels=row.labels or {},
        cooldown_seconds=row.cooldown_seconds,
        auto_resolve=row.auto_resolve,
        enabled=row.enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/alerts", response_model=AlertOut, status_code=201)
def create_alert(body: AlertIn, project_id: IngestProjectId, db: DbSession) -> AlertOut:
    row = AlertService(db).submit_external(project_id, body)
    return _alert(row, AlertService(db).history(row.id))


@router.get("/alerts", response_model=Page[AlertOut])
def list_alerts(
    project_id: ProjectId,
    db: DbSession,
    status: str | None = None,
    severity: str | None = None,
    service: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[AlertOut]:
    rows, total = AlertService(db).list_alerts(
        project_id,
        status=status,
        severity=severity,
        service=service,
        page=page,
        page_size=page_size,
    )
    return Page(items=[_alert(row) for row in rows], total=total, page=page, page_size=page_size)


@router.get("/alerts/{alert_id}", response_model=AlertOut)
def get_alert(alert_id: str, project_id: ProjectId, db: DbSession) -> AlertOut:
    service = AlertService(db)
    row = service.get_alert(project_id, alert_id)
    return _alert(row, service.history(row.id))


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge_alert(alert_id: str, project_id: ProjectId, db: DbSession) -> AlertOut:
    service = AlertService(db)
    row = service.acknowledge(project_id, alert_id, "user")
    return _alert(row, service.history(row.id))


@router.post("/alerts/{alert_id}/resolve", response_model=AlertOut)
def resolve_alert(alert_id: str, project_id: ProjectId, db: DbSession) -> AlertOut:
    service = AlertService(db)
    row = service.resolve(project_id, alert_id, "user")
    return _alert(row, service.history(row.id))


@router.get("/alert-rules", response_model=list[AlertRuleOut])
def list_rules(project_id: ProjectId, db: DbSession) -> list[AlertRuleOut]:
    return [_rule(row) for row in AlertService(db).list_rules(project_id)]


@router.post("/alert-rules", response_model=AlertRuleOut, status_code=201)
def create_rule(body: AlertRuleIn, project_id: ProjectId, db: DbSession) -> AlertRuleOut:
    return _rule(AlertService(db).create_rule(project_id, body))


@router.put("/alert-rules/{rule_id}", response_model=AlertRuleOut)
def update_rule(rule_id: str, body: AlertRuleIn, project_id: ProjectId, db: DbSession) -> AlertRuleOut:
    return _rule(AlertService(db).update_rule(project_id, rule_id, body))


@router.delete("/alert-rules/{rule_id}", status_code=204)
def delete_rule(rule_id: str, project_id: ProjectId, db: DbSession) -> None:
    AlertService(db).delete_rule(project_id, rule_id)


@router.get("/notification-channels", response_model=list[ChannelOut])
def list_channels(project_id: ProjectId, db: DbSession) -> list[ChannelOut]:
    return [_channel(row) for row in AlertService(db).list_channels(project_id)]


@router.post("/notification-channels", response_model=ChannelOut, status_code=201)
def create_channel(body: ChannelIn, project_id: ProjectId, db: DbSession) -> ChannelOut:
    try:
        return _channel(AlertService(db).create_channel(project_id, body))
    except WebhookError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/notification-channels/{channel_id}", status_code=204)
def delete_channel(channel_id: str, project_id: ProjectId, db: DbSession) -> None:
    AlertService(db).delete_channel(project_id, channel_id)


def _channel(row) -> ChannelOut:
    return ChannelOut(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        channel_type=row.channel_type,
        url=str((row.config or {}).get("url") or ""),
        enabled=row.enabled,
        created_at=row.created_at,
    )
