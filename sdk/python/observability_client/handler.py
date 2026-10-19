from __future__ import annotations

import logging

from observability_client.client import ObservabilityClient


class ObservabilityHandler(logging.Handler):
    """Forward standard logging records without reporting the client's own failures."""

    def __init__(self, client: ObservabilityClient, level: int = logging.INFO) -> None:
        super().__init__(level)
        self.client = client

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(("observability_client", "opentelemetry")):
            return
        try:
            exception = record.exc_info[1] if record.exc_info else None
            self.client.log(
                record.levelname,
                record.getMessage(),
                attributes={"logger": record.name},
                exception=exception,
                logger_name=record.name,
            )
        except Exception:
            self.handleError(record)
