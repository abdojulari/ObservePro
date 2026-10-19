from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.telemetry.severity import ALERT_SEVERITIES

AlertSeverity = Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL", "EMERGENCY"]
AlertStatus = Literal["PENDING", "FIRING", "ACKNOWLEDGED", "RESOLVED"]
ConditionType = Literal[
    "error_count",
    "error_rate",
    "p95_latency",
    "metric_threshold",
    "service_silence",
    "log_severity",
    "event_match",
]
Comparison = Literal["gt", "gte", "lt", "lte"]


class AlertIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    message: str = Field(default="", max_length=8000)
    severity: AlertSeverity = "HIGH"
    service: str | None = Field(default=None, max_length=200)
    environment: str | None = Field(default=None, max_length=100)
    fingerprint: str | None = Field(default=None, max_length=200)
    attributes: dict[str, Any] = Field(default_factory=dict)
    project_id: str | None = Field(default=None, description="Ignored. Taken from the API key.")

    @field_validator("severity", mode="before")
    @classmethod
    def _severity(cls, value: str) -> str:
        key = str(value).strip().upper()
        if key not in ALERT_SEVERITIES:
            raise ValueError(f"severity must be one of {', '.join(ALERT_SEVERITIES)}")
        return key


class AlertHistoryOut(BaseModel):
    id: str
    from_status: str | None = None
    to_status: str
    message: str
    actor: str | None = None
    created_at: datetime


class AlertOut(BaseModel):
    id: str
    project_id: str
    rule_id: str | None = None
    fingerprint: str
    title: str
    message: str
    severity: str
    status: str
    service: str | None = None
    environment: str | None = None
    trigger_value: float | None = None
    threshold: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    first_seen: datetime
    last_seen: datetime
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    history: list[AlertHistoryOut] = Field(default_factory=list)


class AlertRuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    condition_type: ConditionType
    threshold: float = 0
    comparison: Comparison = "gt"
    window_seconds: int = Field(default=300, ge=30, le=7 * 24 * 3600)
    severity: AlertSeverity = "HIGH"
    service: str | None = Field(default=None, max_length=200)
    environment: str | None = Field(default=None, max_length=100)
    metric_name: str | None = Field(default=None, max_length=300)
    event_name: str | None = Field(default=None, max_length=200)
    log_severity: str | None = Field(default=None, max_length=16)
    labels: dict[str, str] = Field(default_factory=dict)
    cooldown_seconds: int = Field(default=300, ge=0, le=7 * 24 * 3600)
    auto_resolve: bool = True
    enabled: bool = True

    @field_validator("severity", mode="before")
    @classmethod
    def _severity(cls, value: str) -> str:
        key = str(value).strip().upper()
        if key not in ALERT_SEVERITIES:
            raise ValueError(f"severity must be one of {', '.join(ALERT_SEVERITIES)}")
        return key

    @field_validator("log_severity")
    @classmethod
    def _log_severity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        key = value.strip().upper()
        aliases = {"WARNING": "WARN", "CRITICAL": "FATAL"}
        return aliases.get(key, key)

    @model_validator(mode="after")
    def _condition_fields(self) -> AlertRuleIn:
        if self.condition_type == "service_silence" and not self.service:
            raise ValueError("service_silence rules require a service name")
        if self.condition_type == "metric_threshold" and not self.metric_name:
            raise ValueError("metric_threshold rules require metric_name")
        if self.condition_type == "event_match" and not self.event_name:
            raise ValueError("event_match rules require event_name")
        if self.condition_type == "log_severity" and not self.log_severity:
            raise ValueError("log_severity rules require log_severity")
        return self


class AlertRuleOut(AlertRuleIn):
    id: str
    project_id: str
    created_at: datetime
    updated_at: datetime


class ChannelIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    channel_type: Literal["webhook"] = "webhook"
    url: str = Field(min_length=8, max_length=2000)
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class ChannelOut(BaseModel):
    id: str
    project_id: str
    name: str
    channel_type: str
    url: str
    enabled: bool
    created_at: datetime


class DeliveryOut(BaseModel):
    id: str
    alert_id: str
    channel_id: str | None = None
    status: str
    attempt: int
    response_code: int | None = None
    error: str | None = None
    created_at: datetime
