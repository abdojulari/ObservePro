from datetime import datetime, timedelta, timezone

from app.services.retention import run_retention


def test_retention_deletes_old_logs_and_keeps_recent(client, api_key, reader):
    created = client.post(
        "/api/v1/logs",
        headers=api_key["headers"],
        json={"message": "keep me", "severity": "INFO", "service": "api"},
    )
    assert created.status_code == 201
    old = client.post(
        "/api/v1/logs",
        headers=api_key["headers"],
        json={"message": "drop me", "severity": "INFO", "service": "api"},
    ).json()
    from app.db.session import get_session
    from app.models import LogEntry

    db = get_session()
    row = db.get(LogEntry, old["id"])
    row.timestamp = datetime(2020, 1, 1, tzinfo=timezone.utc)
    db.commit()
    removed = run_retention(db)
    db.close()
    assert removed["logs"] >= 1
    listed = client.get("/api/v1/logs", headers=reader)
    messages = [item["message"] for item in listed.json()["items"]]
    assert "keep me" in messages
    assert "drop me" not in messages


def test_rollback_discards_uncommitted_ingest(client, api_key):
    from sqlalchemy import func, select

    from app.db.session import get_session
    from app.models import LogEntry
    from app.schemas.telemetry import LogIn
    from app.services.ingestion import IngestionService

    db = get_session()
    before = int(
        db.scalar(select(func.count()).select_from(LogEntry).where(LogEntry.message == "rollback-me")) or 0
    )
    IngestionService(db).ingest_logs(api_key["project_id"], [LogIn(message="rollback-me", severity="INFO")])
    db.rollback()
    after = int(
        db.scalar(select(func.count()).select_from(LogEntry).where(LogEntry.message == "rollback-me")) or 0
    )
    db.close()
    assert after == before


def test_rate_limit(client, api_key):
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.rate_limit_per_minute
    settings.rate_limit_per_minute = 2
    try:
        statuses = [
            client.post(
                "/api/v1/logs",
                headers=api_key["headers"],
                json={"message": f"n{index}", "severity": "INFO"},
            ).status_code
            for index in range(3)
        ]
    finally:
        settings.rate_limit_per_minute = original
    assert statuses[:2] == [201, 201]
    assert statuses[2] == 429


def test_redis_failure_does_not_block_ingest(client, api_key):
    from app.services.redis_client import init_redis

    init_redis("redis://127.0.0.1:1/0")
    response = client.post(
        "/api/v1/logs",
        headers=api_key["headers"],
        json={"message": "still stored", "severity": "INFO"},
    )
    assert response.status_code == 201
    ready = client.get("/ready")
    assert ready.json()["redis"] == "degraded"
    assert ready.status_code == 200
