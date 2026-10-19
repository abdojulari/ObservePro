from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from datetime import datetime, timezone

_SECRET_PATTERNS = (
    re.compile(r"op_[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-+/=]+"),
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[=:]\s*\S+"),
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key in ("request_id", "path", "status_code", "method"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, default=str)


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = message
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretRedactionFilter())
    root.addHandler(handler)
    root.setLevel(level.upper())
    for name in ("uvicorn.access", "opentelemetry", "grpc"):
        logging.getLogger(name).setLevel(logging.WARNING)


def safe_log_text(value: object, limit: int = 300) -> str:
    text = str(value).replace("\r", "\\r").replace("\n", "\\n")
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def compare_digest(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
