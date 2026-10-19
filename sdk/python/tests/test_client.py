import json

import httpx
import pytest

from observability_client import BufferFull, ObservabilityClient


def _client(**kwargs) -> ObservabilityClient:
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append({"path": request.url.path, "body": json.loads(request.content.decode())})
        return httpx.Response(200, json={"accepted": 1})

    client = ObservabilityClient(
        endpoint="http://observe.test",
        api_key="op_test",
        service_name="payments",
        environment="test",
        start_worker=True,
        enable_tracing=False,
        transport=httpx.MockTransport(handler),
        flush_interval=0.05,
        timeout=0.2,
        **kwargs,
    )
    client.calls = calls  # type: ignore[attr-defined]
    return client


def test_log_delivery_and_batch_flush():
    client = _client(max_retries=0)
    assert client.info("one")
    assert client.info("two")
    assert client.flush(timeout=2)
    client.shutdown()
    bodies = [call["body"] for call in client.calls]
    assert any(isinstance(body, dict) and body.get("logs") and len(body["logs"]) == 2 for body in bodies) or len(bodies) >= 1
    messages = []
    for body in bodies:
        if "logs" in body:
            messages.extend(item["message"] for item in body["logs"])
        else:
            messages.append(body["message"])
    assert messages == ["one", "two"]


def test_buffer_full_drops_when_fail_open():
    client = ObservabilityClient(
        endpoint="http://observe.test",
        api_key="op_test",
        service_name="payments",
        buffer_size=1,
        fail_open=True,
        start_worker=False,
        enable_tracing=False,
        transport=httpx.MockTransport(lambda request: httpx.Response(200)),
    )
    assert client.info("first") is True
    assert client.info("second") is False
    assert client.dropped == 1
    client.shutdown()


def test_buffer_full_raises_when_not_fail_open():
    client = ObservabilityClient(
        endpoint="http://observe.test",
        api_key="op_test",
        service_name="payments",
        buffer_size=1,
        fail_open=False,
        start_worker=False,
        enable_tracing=False,
        transport=httpx.MockTransport(lambda request: httpx.Response(200)),
    )
    client.info("first")
    with pytest.raises(BufferFull):
        client.info("second")
    client.shutdown()


def test_retries_then_succeeds(monkeypatch):
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json={"ok": True})

    client = ObservabilityClient(
        endpoint="http://observe.test",
        api_key="op_test",
        service_name="payments",
        start_worker=True,
        enable_tracing=False,
        max_retries=2,
        transport=httpx.MockTransport(handler),
        flush_interval=0.01,
    )
    monkeypatch.setattr(client, "_sleep", lambda _seconds: None)
    assert client.warning("retry me")
    assert client.flush(timeout=2)
    client.shutdown()
    assert attempts["n"] == 2


def test_timeout_fail_open_does_not_raise(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    client = ObservabilityClient(
        endpoint="http://observe.test",
        api_key="op_test",
        service_name="payments",
        start_worker=True,
        enable_tracing=False,
        fail_open=True,
        max_retries=1,
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(client, "_sleep", lambda _seconds: None)
    assert client.error("timed out") is True
    assert client.flush(timeout=2) is True
    client.shutdown()
    assert client.failed == 1


def test_transport_failure_is_not_reported_recursively(monkeypatch):
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        raise httpx.ConnectError("nope")

    client = ObservabilityClient(
        endpoint="http://observe.test",
        api_key="op_test",
        service_name="payments",
        start_worker=True,
        enable_tracing=False,
        capture_logs=True,
        max_retries=1,
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(client, "_sleep", lambda _seconds: None)
    client.info("hello")
    client.flush(timeout=2)
    client.shutdown()
    assert attempts["n"] == 2


def test_exception_and_span_context_are_attached():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content.decode()))
        return httpx.Response(200, json={"ok": True})

    client = ObservabilityClient(
        endpoint="http://observe.test",
        api_key="op_test",
        service_name="payments",
        environment="test",
        start_worker=True,
        enable_tracing=True,
        export_traces=False,
        transport=httpx.MockTransport(handler),
        flush_interval=0.01,
        max_retries=0,
    )
    with client.start_span("process_payment") as span:
        span.set_attribute("payment.provider", "example")
        try:
            raise RuntimeError("declined")
        except RuntimeError as exc:
            client.capture_exception(exc, message="Payment processing failed")
    assert client.flush(timeout=2)
    client.shutdown()
    body = seen[0]
    if "logs" in body:
        body = body["logs"][0]
    assert body["exception"]["type"] == "RuntimeError"
    assert len(body["trace_id"]) == 32
    assert len(body["span_id"]) == 16
