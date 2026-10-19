TRACE = "0123456789abcdef0123456789abcdef"
SPAN = "0123456789abcdef"
CHILD = "fedcba9876543210"


def test_otlp_json_trace_and_correlated_log(client, api_key, reader):
    traces = client.post(
        "/v1/traces",
        headers={**api_key["headers"], "Content-Type": "application/json"},
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
                                    "traceId": TRACE,
                                    "spanId": SPAN,
                                    "name": "POST /pay",
                                    "kind": 2,
                                    "startTimeUnixNano": "1760000000000000000",
                                    "endTimeUnixNano": "1760000000150000000",
                                    "status": {"code": 1},
                                    "attributes": [
                                        {"key": "http.request.method", "value": {"stringValue": "POST"}}
                                    ],
                                },
                                {
                                    "traceId": TRACE,
                                    "spanId": CHILD,
                                    "parentSpanId": SPAN,
                                    "name": "charge",
                                    "kind": 3,
                                    "startTimeUnixNano": "1760000000020000000",
                                    "endTimeUnixNano": "1760000000100000000",
                                    "status": {"code": 2, "message": "declined"},
                                },
                            ]
                        }
                    ],
                }
            ]
        },
    )
    assert traces.status_code == 200, traces.text
    listed = client.get("/api/v1/traces", headers=reader)
    assert listed.json()["total"] == 1
    summary = listed.json()["items"][0]
    assert summary["trace_id"] == TRACE
    assert summary["status"] == "error"
    assert summary["span_count"] == 2
    detail = client.get(f"/api/v1/traces/{TRACE}", headers=reader)
    assert detail.status_code == 200
    assert len(detail.json()["spans"]) == 2

    logged = client.post(
        "/api/v1/logs",
        headers=api_key["headers"],
        json={
            "message": "charge failed",
            "severity": "ERROR",
            "service": "payment-service",
            "trace_id": TRACE,
            "span_id": CHILD,
        },
    )
    assert logged.status_code == 201
    again = client.get(f"/api/v1/traces/{TRACE}", headers=reader)
    assert again.json()["logs"][0]["message"] == "charge failed"
    spans = client.get(f"/api/v1/traces/{TRACE}/spans", headers=reader)
    assert any(span["parent_span_id"] == SPAN for span in spans.json())


def test_histogram_summary_does_not_average_percentiles(client, api_key, reader):
    response = client.post(
        "/api/v1/metrics",
        headers=api_key["headers"],
        json={
            "name": "http.server.duration",
            "type": "histogram",
            "service": "payment-service",
            "unit": "ms",
            "bucket_bounds": [5, 10],
            "bucket_counts": [0, 10, 0],
            "count": 10,
            "sum": 75,
        },
    )
    assert response.status_code == 201, response.text
    summary = client.get(
        "/api/v1/metrics/summary",
        headers=reader,
        params={"name": "http.server.duration", "range": "24h"},
    )
    assert summary.status_code == 200, summary.text
    assert summary.json()["p50"] == 7.5
    names = client.get("/api/v1/metrics/names", headers=reader)
    assert names.json()[0]["name"] == "http.server.duration"
    series = client.get(
        "/api/v1/metrics/timeseries",
        headers=reader,
        params={"name": "http.server.duration", "range": "24h"},
    )
    assert series.json()["points"]


def test_otlp_protobuf_trace_round_trip(client, api_key, reader):
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
    from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
    from opentelemetry.proto.resource.v1.resource_pb2 import Resource
    from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span

    request = ExportTraceServiceRequest(
        resource_spans=[
            ResourceSpans(
                resource=Resource(
                    attributes=[
                        KeyValue(key="service.name", value=AnyValue(string_value="checkout")),
                    ]
                ),
                scope_spans=[
                    ScopeSpans(
                        spans=[
                            Span(
                                trace_id=bytes.fromhex(TRACE),
                                span_id=bytes.fromhex(SPAN),
                                name="GET /health",
                                kind=Span.SPAN_KIND_SERVER,
                                start_time_unix_nano=1760000000000000000,
                                end_time_unix_nano=1760000000005000000,
                            )
                        ]
                    )
                ],
            )
        ]
    )
    response = client.post(
        "/v1/traces",
        headers={**api_key["headers"], "Content-Type": "application/x-protobuf"},
        content=request.SerializeToString(),
    )
    assert response.status_code == 200, response.text
    detail = client.get(f"/api/v1/traces/{TRACE}", headers=reader)
    assert detail.status_code == 200
    assert detail.json()["service"] == "checkout"
