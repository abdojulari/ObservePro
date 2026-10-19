def test_end_to_end_dashboard_contract(client, admin):
    from datetime import datetime, timezone

    start_ns = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
    end_ns = start_ns + 20_000_000
    project = client.post("/api/v1/projects", headers=admin, json={"name": "Checkout", "slug": "checkout"}).json()
    key = client.post(
        "/api/v1/api-keys",
        headers=admin,
        json={"name": "sample-app", "project_id": project["id"]},
    ).json()
    ingest = {"Authorization": f"Bearer {key['secret']}"}
    reader = {**admin, "X-Project-Id": project["id"]}

    log = client.post(
        "/api/v1/logs",
        headers=ingest,
        json={
            "message": "Payment processing failed",
            "severity": "ERROR",
            "service": "payment-service",
            "environment": "production",
            "trace_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "span_id": "bbbbbbbbbbbbbbbb",
            "attributes": {"order_id": "order-123"},
        },
    )
    assert log.status_code == 201

    trace = client.post(
        "/v1/traces",
        headers={**ingest, "Content-Type": "application/json"},
        json={
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "payment-service"}},
                            {"key": "deployment.environment.name", "value": {"stringValue": "production"}},
                        ]
                    },
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "traceId": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                                    "spanId": "bbbbbbbbbbbbbbbb",
                                    "name": "process_payment",
                                    "kind": 2,
                                    "startTimeUnixNano": str(start_ns),
                                    "endTimeUnixNano": str(end_ns),
                                    "status": {"code": 2, "message": "failed"},
                                }
                            ]
                        }
                    ],
                }
            ]
        },
    )
    assert trace.status_code == 200

    metric = client.post(
        "/api/v1/metrics",
        headers=ingest,
        json={
            "name": "payment.attempts",
            "type": "counter",
            "value": 1,
            "service": "payment-service",
            "environment": "production",
            "temporality": "delta",
        },
    )
    assert metric.status_code == 201

    event = client.post(
        "/api/v1/events",
        headers=ingest,
        json={"name": "payment.failed", "message": "provider error", "service": "payment-service"},
    )
    assert event.status_code == 201

    alert = client.post(
        "/api/v1/alerts",
        headers=ingest,
        json={
            "title": "Payment processing failure",
            "message": "Payment provider is returning errors",
            "severity": "CRITICAL",
            "service": "payment-service",
            "fingerprint": "payment-processing-failure",
        },
    )
    assert alert.status_code == 201

    logs = client.get("/api/v1/logs", headers=reader, params={"trace_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"})
    assert logs.json()["total"] == 1
    detail = client.get("/api/v1/traces/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", headers=reader)
    assert detail.status_code == 200
    assert detail.json()["logs"][0]["id"] == log.json()["id"]
    assert client.get("/api/v1/metrics", headers=reader, params={"name": "payment.attempts"}).json()["total"] == 1
    assert client.get("/api/v1/events", headers=reader).json()["total"] == 1
    alerts = client.get("/api/v1/alerts", headers=reader)
    assert alerts.json()["total"] == 1

    overview = client.get("/api/v1/analytics/overview", headers=reader, params={"range": "7d"})
    assert overview.status_code == 200
    body = overview.json()
    assert body["logs"]["error"] >= 1
    assert body["alerts"]["active"] >= 1
    assert body["traffic"]["has_data"] is True
    breakdown = client.get("/api/v1/analytics/breakdown", headers=reader, params={"range": "7d"})
    assert breakdown.json()["top_errors"][0]["message"] == "Payment processing failed"
    services = client.get("/api/v1/services", headers=reader, params={"range": "7d"})
    assert any(item["name"] == "payment-service" for item in services.json())

    ack = client.post(f"/api/v1/alerts/{alert.json()['id']}/acknowledge", headers=reader)
    assert ack.json()["status"] == "ACKNOWLEDGED"
    resolved = client.post(f"/api/v1/alerts/{alert.json()['id']}/resolve", headers=reader)
    assert resolved.json()["status"] == "RESOLVED"
