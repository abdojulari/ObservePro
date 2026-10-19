from __future__ import annotations

SEVERITY_NUMBERS: dict[str, int] = {
    "TRACE": 1,
    "DEBUG": 5,
    "INFO": 9,
    "WARN": 13,
    "WARNING": 13,
    "ERROR": 17,
    "FATAL": 21,
    "CRITICAL": 21,
}

SEVERITY_ORDER = ("TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL")

# Alert severities and the OpenTelemetry log severity they correspond to.
ALERT_SEVERITIES = ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL", "EMERGENCY")
ALERT_TO_OTEL: dict[str, tuple[str, int]] = {
    "INFO": ("INFO", 9),
    "LOW": ("INFO", 10),
    "MEDIUM": ("WARN", 13),
    "HIGH": ("ERROR", 17),
    "CRITICAL": ("FATAL", 21),
    "EMERGENCY": ("FATAL", 24),
}


def normalize_severity(text: str | None, number: int | None = None) -> tuple[str, int]:
    if text:
        key = text.strip().upper()
        if key in SEVERITY_NUMBERS:
            canonical = {"WARNING": "WARN", "CRITICAL": "FATAL"}.get(key, key)
            return canonical, SEVERITY_NUMBERS[key]
    if number is not None:
        clamped = max(1, min(24, int(number)))
        return number_to_text(clamped), clamped
    return "INFO", 9


def number_to_text(number: int) -> str:
    if number <= 4:
        return "TRACE"
    if number <= 8:
        return "DEBUG"
    if number <= 12:
        return "INFO"
    if number <= 16:
        return "WARN"
    if number <= 20:
        return "ERROR"
    return "FATAL"


def alert_to_otel(severity: str) -> tuple[str, int]:
    return ALERT_TO_OTEL.get(severity.upper(), ("ERROR", 17))
