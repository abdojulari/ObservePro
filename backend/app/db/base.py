from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, TypeDecorator
from sqlalchemy.orm import DeclarativeBase


def new_id() -> str:
    return str(uuid.uuid4())


class UTCDateTime(TypeDecorator):
    """Store UTC datetimes as naive UTC and return timezone-aware values."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass
