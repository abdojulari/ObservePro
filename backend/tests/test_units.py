from app.core.redaction import redact
from app.core.security import hash_password, verify_password
from app.telemetry.histogram import histogram_quantile, percentile
from app.telemetry.severity import alert_to_otel, normalize_severity


def test_password_hash_is_not_reversible_plaintext():
    encoded = hash_password("correct horse battery")
    assert "correct horse" not in encoded
    assert verify_password("correct horse battery", encoded)
    assert not verify_password("nope", encoded)


def test_severity_normalization():
    assert normalize_severity("warning") == ("WARN", 13)
    assert normalize_severity("CRITICAL") == ("FATAL", 21)
    assert normalize_severity(None, 17) == ("ERROR", 17)
    assert normalize_severity(None, 22) == ("FATAL", 22)
    assert alert_to_otel("CRITICAL") == ("FATAL", 21)
    assert alert_to_otel("EMERGENCY") == ("FATAL", 24)


def test_histogram_quantile_uses_buckets_not_averages():
    bounds = [5, 10]
    counts = [0, 10, 0]
    assert histogram_quantile(0.5, bounds, counts) == 7.5
    assert percentile([10, 20, 30, 40], 0.5) == 25


def test_redaction_covers_nested_secrets():
    cleaned = redact({"user": "ada", "password": "hunter2", "nested": {"api_key": "abc", "ok": 1}})
    assert cleaned["password"] == "[REDACTED]"
    assert cleaned["nested"]["api_key"] == "[REDACTED]"
    assert cleaned["nested"]["ok"] == 1
    assert cleaned["user"] == "ada"
