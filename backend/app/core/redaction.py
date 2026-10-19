from __future__ import annotations

import json
from typing import Any

SENSITIVE_KEYS = {
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "refresh_token",
    "id_token",
    "credit_card",
    "card_number",
    "ssn",
    "private_key",
    "cookie",
    "set_cookie",
    "session",
    "session_id",
}

_MAX_DEPTH = 20


def _is_sensitive(key: str) -> bool:
    normalized = key.lower().replace("-", "_").replace(" ", "_")
    if normalized in SENSITIVE_KEYS:
        return True
    return normalized.endswith(("_token", "_secret", "_password", "_api_key"))


def redact(value: Any, depth: int = 0) -> Any:
    if depth > _MAX_DEPTH:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive(key_text):
                cleaned[key_text] = "[REDACTED]"
            else:
                cleaned[key_text] = redact(item, depth + 1)
        return cleaned
    if isinstance(value, list):
        return [redact(item, depth + 1) for item in value[:500]]
    if isinstance(value, tuple):
        return [redact(item, depth + 1) for item in value[:500]]
    return value


def json_size(value: Any) -> int:
    return len(json.dumps(value, default=str, separators=(",", ":")))
