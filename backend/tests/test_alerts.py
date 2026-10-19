def test_external_alert_dedup_and_lifecycle(client, api_key, reader):
    payload = {
        "title": "Payment failure rate exceeded threshold",
        "message": "Payment failures are above the configured threshold",
        "severity": "CRITICAL",
        "service": "payment-service",
        "environment": "production",
        "fingerprint": "payment-failure-rate",
        "attributes": {"failure_rate": 12.5, "threshold": 5},
    }
    first = client.post("/api/v1/alerts", headers=api_key["headers"], json=payload)
    second = client.post("/api/v1/alerts", headers=api_key["headers"], json=payload)
    assert first.status_code == 201, first.text
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["status"] == "FIRING"
    assert any(item["to_status"] == "PENDING" for item in first.json()["history"])

    acknowledged = client.post(f"/api/v1/alerts/{first.json()['id']}/acknowledge", headers=reader)
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "ACKNOWLEDGED"
    resolved = client.post(f"/api/v1/alerts/{first.json()['id']}/resolve", headers=reader)
    assert resolved.json()["status"] == "RESOLVED"

    reopened = client.post("/api/v1/alerts", headers=api_key["headers"], json=payload)
    assert reopened.json()["id"] != first.json()["id"]
    assert reopened.json()["status"] == "FIRING"


def test_rule_evaluation_cooldown_and_webhook(client, api_key, reader, monkeypatch):
    calls = []

    def fake_post(url, payload, headers, timeout):
        calls.append(payload)
        return 204

    monkeypatch.setattr("app.alerting.notifier.post_webhook", fake_post)
    channel = client.post(
        "/api/v1/notification-channels",
        headers=reader,
        json={"name": "ops", "url": "http://localhost:9/hooks"},
    )
    assert channel.status_code == 201, channel.text
    rule = client.post(
        "/api/v1/alert-rules",
        headers=reader,
        json={
            "name": "errors high",
            "condition_type": "error_count",
            "threshold": 1,
            "comparison": "gte",
            "window_seconds": 3600,
            "severity": "HIGH",
            "service": "payment-service",
            "cooldown_seconds": 3600,
            "auto_resolve": True,
        },
    )
    assert rule.status_code == 201, rule.text
    client.post(
        "/api/v1/logs",
        headers=api_key["headers"],
        json={"message": "failed once", "severity": "ERROR", "service": "payment-service"},
    )
    from app.alerting.engine import AlertService
    from app.db.session import session_scope

    with session_scope() as db:
        assert AlertService(db).evaluate_all() == 1
    pending = client.get("/api/v1/alerts", headers=reader)
    assert pending.json()["items"][0]["status"] == "PENDING"
    with session_scope() as db:
        AlertService(db).deliver_pending()
    assert calls and calls[0]["title"] == "errors high"
    firing = client.get("/api/v1/alerts", headers=reader)
    assert firing.json()["items"][0]["status"] == "FIRING"

    client.post(f"/api/v1/alerts/{firing.json()['items'][0]['id']}/resolve", headers=reader)
    client.post(
        "/api/v1/logs",
        headers=api_key["headers"],
        json={"message": "failed again", "severity": "ERROR", "service": "payment-service"},
    )
    with session_scope() as db:
        AlertService(db).evaluate_all()
    statuses = [item["status"] for item in client.get("/api/v1/alerts", headers=reader).json()["items"]]
    assert statuses.count("FIRING") == 0
    assert "RESOLVED" in statuses


def test_rule_requires_condition_fields(client, reader):
    response = client.post(
        "/api/v1/alert-rules",
        headers=reader,
        json={"name": "silence", "condition_type": "service_silence", "threshold": 1, "window_seconds": 60},
    )
    assert response.status_code == 422
