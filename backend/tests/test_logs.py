def _log(secret, **overrides):
    payload = {
        "timestamp": "2026-10-18T12:00:00Z",
        "severity": "ERROR",
        "message": "Payment processing failed",
        "service": "payment-service",
        "environment": "production",
        "attributes": {"order_id": "order-123", "password": "super-secret"},
    }
    payload.update(overrides)
    return payload


def test_log_ingestion_retrieval_and_redaction(client, api_key, reader):
    created = client.post("/api/v1/logs", headers=api_key["headers"], json=_log(api_key))
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["severity"] == "ERROR"
    assert body["severity_number"] == 17
    assert body["attributes"]["password"] == "[REDACTED]"
    assert body["attributes"]["order_id"] == "order-123"
    assert body["project_id"] == api_key["project_id"]

    listed = client.get("/api/v1/logs", headers=reader, params={"q": "Payment", "severity": "ERROR"})
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    fetched = client.get(f"/api/v1/logs/{body['id']}", headers=reader)
    assert fetched.status_code == 200
    assert fetched.json()["message"] == "Payment processing failed"


def test_batch_partial_acceptance(client, api_key, reader):
    response = client.post(
        "/api/v1/logs/batch",
        headers=api_key["headers"],
        json={
            "logs": [
                _log(api_key, message="one", severity="INFO"),
                {"message": "too old", "severity": "INFO", "timestamp": "1990-01-01T00:00:00Z"},
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] == 1
    assert body["rejected"] == 1
    listed = client.get("/api/v1/logs", headers=reader)
    assert listed.json()["total"] == 1


def test_validation_and_ignored_project_id(client, api_key, reader):
    rejected = client.post(
        "/api/v1/logs",
        headers=api_key["headers"],
        json={"message": "nope", "severity": "NOPE"},
    )
    assert rejected.status_code == 422
    created = client.post(
        "/api/v1/logs",
        headers=api_key["headers"],
        json=_log(api_key, project_id="someone-elses-project", message="scoped"),
    )
    assert created.status_code == 201
    assert created.json()["project_id"] == api_key["project_id"]


def test_idempotency_key_replays_original_log(client, api_key):
    headers = {**api_key["headers"], "Idempotency-Key": "payment-log-1"}
    payload = _log(api_key, event_id="evt-1")
    first = client.post("/api/v1/logs", headers=headers, json=payload)
    second = client.post("/api/v1/logs", headers=headers, json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    conflict = client.post(
        "/api/v1/logs",
        headers=headers,
        json=_log(api_key, message="different", event_id="evt-2"),
    )
    assert conflict.status_code == 409


def test_filters(client, api_key, reader):
    client.post("/api/v1/logs", headers=api_key["headers"], json=_log(api_key, severity="INFO", message="hello info", service="a"))
    client.post(
        "/api/v1/logs",
        headers=api_key["headers"],
        json=_log(api_key, severity="ERROR", message="hello error", service="b", trace_id="abc123"),
    )
    errors = client.get("/api/v1/logs", headers=reader, params={"severity": "ERROR", "service": "b", "trace_id": "abc123"})
    assert errors.json()["total"] == 1
    assert errors.json()["items"][0]["service"] == "b"


def test_warning_alias_and_exception(client, api_key):
    response = client.post(
        "/api/v1/logs",
        headers=api_key["headers"],
        json=_log(
            api_key,
            severity="WARNING",
            exception={"type": "RuntimeError", "message": "boom", "stacktrace": "line 1"},
        ),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["severity"] == "WARN"
    assert body["exception"]["type"] == "RuntimeError"
