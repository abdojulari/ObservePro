from __future__ import annotations

from datetime import datetime, timedelta
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from app.core.security import utcnow

T = TypeVar("T")

RANGE_WINDOWS = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class ItemError(BaseModel):
    index: int
    detail: str


class BatchResult(BaseModel):
    accepted: int
    rejected: int
    errors: list[ItemError]
    ids: list[str]


def resolve_window(
    range_key: str | None,
    start: datetime | None,
    end: datetime | None,
) -> tuple[datetime, datetime]:
    now = utcnow()
    if start or end:
        return start or (now - timedelta(hours=1)), end or now
    window = RANGE_WINDOWS.get(range_key or "1h", RANGE_WINDOWS["1h"])
    return now - window, now


def bucket_seconds(start: datetime, end: datetime) -> int:
    span = max(60, int((end - start).total_seconds()))
    if span <= 3600:
        return 60
    if span <= 6 * 3600:
        return 300
    if span <= 24 * 3600:
        return 3600
    return 6 * 3600


class PlatformStatus(BaseModel):
    version: str
    environment: str
    retention_days: int
    rate_limit_per_minute: int
    max_body_bytes: int
    redis: str
    database: str
    storage: str = "sqlite"
    otlp_grpc_enabled: bool
    ingestion_semantics: str = "at-least-once"
    limitations: list[str] = Field(default_factory=list)
