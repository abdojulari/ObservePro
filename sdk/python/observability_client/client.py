from __future__ import annotations

import logging
import queue
import random
import sys
import threading
import time
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("observability_client.transport")

_LEVELS = {
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "WARNING": "WARN",
    "WARN": "WARN",
    "ERROR": "ERROR",
    "CRITICAL": "FATAL",
    "FATAL": "FATAL",
}


class BufferFull(RuntimeError):
    """Raised when the send buffer is full and fail_open is disabled."""


class _SpanAdapter:
    def __init__(self, span: Any) -> None:
        self._span = span

    def set_attribute(self, key: str, value: Any) -> None:
        if self._span is not None:
            self._span.set_attribute(key, _otel_value(value))

    def record_exception(self, exc: BaseException) -> None:
        if self._span is not None and hasattr(self._span, "record_exception"):
            self._span.record_exception(exc)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._span, name)


def _otel_value(value: Any) -> Any:
    if isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


class ObservabilityClient:
    """Queue telemetry locally and deliver it in the background.

    ``info`` and the other log methods only enqueue. They do not wait on the
    network. When the buffer is full the new event is dropped. Set
    ``fail_open=False`` to raise :class:`BufferFull` instead. Transport errors
    are logged on ``observability_client.transport`` and are not reported back
    through this client.
    """

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        service_name: str,
        environment: str = "production",
        *,
        service_version: str | None = None,
        buffer_size: int = 1000,
        batch_size: int = 100,
        flush_interval: float = 2.0,
        timeout: float = 2.0,
        flush_timeout: float = 5.0,
        max_retries: int = 3,
        fail_open: bool = True,
        console: bool = False,
        enable_tracing: bool = True,
        export_traces: bool = True,
        sample_rate: float = 1.0,
        capture_logs: bool = False,
        start_worker: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.service_name = service_name
        self.environment = environment
        self.service_version = service_version
        self.batch_size = max(1, batch_size)
        self.flush_interval = flush_interval
        self.timeout = timeout
        self.flush_timeout = flush_timeout
        self.max_retries = max(0, max_retries)
        self.fail_open = fail_open
        self.console = console
        self.dropped = 0
        self.failed = 0
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=buffer_size)
        self._stop = threading.Event()
        self._http = httpx.Client(timeout=timeout, transport=transport)
        self._sleep = time.sleep
        self._tracer: Any = None
        self._provider: Any = None
        self._owns_provider = False
        self._handler: logging.Handler | None = None
        if enable_tracing:
            self._setup_tracing(sample_rate=sample_rate, export_traces=export_traces)
        if capture_logs:
            self.install_log_handler()
        self._thread: threading.Thread | None = None
        if start_worker:
            self._thread = threading.Thread(target=self._run, name="observability-client", daemon=False)
            self._thread.start()

    def install_log_handler(self, level: int = logging.INFO) -> ObservabilityHandler:
        from observability_client.handler import ObservabilityHandler

        handler = ObservabilityHandler(self, level=level)
        logging.getLogger().addHandler(handler)
        self._handler = handler
        return handler

    def debug(self, message: str, attributes: dict[str, Any] | None = None) -> bool:
        return self.log("DEBUG", message, attributes=attributes)

    def info(self, message: str, attributes: dict[str, Any] | None = None) -> bool:
        return self.log("INFO", message, attributes=attributes)

    def warning(self, message: str, attributes: dict[str, Any] | None = None) -> bool:
        return self.log("WARN", message, attributes=attributes)

    def error(
        self,
        message: str,
        attributes: dict[str, Any] | None = None,
        exception: BaseException | None = None,
    ) -> bool:
        return self.log("ERROR", message, attributes=attributes, exception=exception)

    def log(
        self,
        severity: str,
        message: str,
        attributes: dict[str, Any] | None = None,
        exception: BaseException | None = None,
        logger_name: str | None = None,
    ) -> bool:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": _LEVELS.get(severity.upper(), "INFO"),
            "message": message,
            "service": self.service_name,
            "environment": self.environment,
            "attributes": dict(attributes or {}),
        }
        if logger_name:
            payload["logger"] = logger_name
        if self.service_version:
            payload["version"] = self.service_version
        trace_id, span_id = self._current_context()
        if trace_id:
            payload["trace_id"] = trace_id
            payload["span_id"] = span_id
        if exception is not None:
            payload["exception"] = {
                "type": type(exception).__name__,
                "message": str(exception),
                "stacktrace": "".join(traceback.format_exception(exception)),
            }
        if self.console:
            print(f"[{payload['severity']}] {message}", file=sys.stderr)
        return self._enqueue({"kind": "log", "body": payload})

    def event(self, name: str, message: str | None = None, attributes: dict[str, Any] | None = None) -> bool:
        body = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "name": name,
            "message": message,
            "service": self.service_name,
            "environment": self.environment,
            "attributes": dict(attributes or {}),
        }
        return self._enqueue({"kind": "event", "body": body})

    def alert(
        self,
        title: str,
        message: str = "",
        severity: str = "HIGH",
        attributes: dict[str, Any] | None = None,
        fingerprint: str | None = None,
    ) -> bool:
        body = {
            "title": title,
            "message": message,
            "severity": severity,
            "service": self.service_name,
            "environment": self.environment,
            "fingerprint": fingerprint,
            "attributes": dict(attributes or {}),
        }
        return self._enqueue({"kind": "alert", "body": body})

    def capture_exception(
        self,
        exc: BaseException,
        message: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> bool:
        span = self._active_span()
        if span is not None and getattr(span, "is_recording", lambda: False)():
            span.record_exception(exc)
            try:
                from opentelemetry.trace import Status, StatusCode

                span.set_status(Status(StatusCode.ERROR, str(exc)))
            except Exception:
                logger.debug("could not set span status", exc_info=True)
        return self.error(message or str(exc), attributes=attributes, exception=exc)

    @contextmanager
    def start_span(self, name: str, attributes: dict[str, Any] | None = None) -> Iterator[_SpanAdapter]:
        if self._tracer is None:
            yield _SpanAdapter(None)
            return
        with self._tracer.start_as_current_span(name) as span:
            adapter = _SpanAdapter(span)
            if attributes:
                for key, value in attributes.items():
                    adapter.set_attribute(key, value)
            try:
                yield adapter
            except Exception as exc:
                adapter.record_exception(exc)
                try:
                    from opentelemetry.trace import Status, StatusCode

                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                except Exception:
                    logger.debug("could not set span status", exc_info=True)
                raise

    def flush(self, timeout: float | None = None) -> bool:
        deadline = time.monotonic() + (self.flush_timeout if timeout is None else timeout)
        while time.monotonic() < deadline:
            if self._queue.unfinished_tasks == 0:
                return True
            self._sleep(0.01)
        return self._queue.unfinished_tasks == 0

    def shutdown(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.flush_timeout)
        if self._handler is not None:
            logging.getLogger().removeHandler(self._handler)
            self._handler = None
        if self._owns_provider and self._provider is not None:
            try:
                self._provider.shutdown()
            except Exception:
                logger.warning("tracer provider shutdown failed", exc_info=True)
        self._http.close()

    def _enqueue(self, item: dict[str, Any]) -> bool:
        try:
            self._queue.put_nowait(item)
            return True
        except queue.Full:
            self.dropped += 1
            if not self.fail_open:
                raise BufferFull("observability buffer is full")
            return False

    def _run(self) -> None:
        while not self._stop.is_set() or not self._queue.empty():
            batch: list[dict[str, Any]] = []
            try:
                batch.append(self._queue.get(timeout=self.flush_interval))
            except queue.Empty:
                continue
            while len(batch) < self.batch_size:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            try:
                self._send_batch(batch)
            finally:
                for _item in batch:
                    self._queue.task_done()

    def _send_batch(self, batch: list[dict[str, Any]]) -> None:
        logs = [item["body"] for item in batch if item["kind"] == "log"]
        events = [item["body"] for item in batch if item["kind"] == "event"]
        alerts = [item["body"] for item in batch if item["kind"] == "alert"]
        if logs:
            path = "/api/v1/logs" if len(logs) == 1 else "/api/v1/logs/batch"
            payload: Any = logs[0] if len(logs) == 1 else {"logs": logs}
            if not self._post(path, payload):
                self.failed += len(logs)
        for event in events:
            if not self._post("/api/v1/events", event):
                self.failed += 1
        for alert in alerts:
            if not self._post("/api/v1/alerts", alert):
                self.failed += 1

    def _post(self, path: str, payload: Any) -> bool:
        delay = 0.05
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._http.post(
                    f"{self.endpoint}{path}",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = RuntimeError(f"status {response.status_code}")
                elif response.status_code >= 400:
                    logger.warning("telemetry rejected with status %s", response.status_code)
                    return False
                else:
                    return True
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
            if attempt < self.max_retries:
                self._sleep(delay + random.uniform(0, delay))
                delay = min(delay * 2, 2.0)
        logger.warning("telemetry delivery failed after retries: %s", last_error)
        if not self.fail_open:
            raise RuntimeError(f"telemetry delivery failed: {last_error}")
        return False

    def _setup_tracing(self, sample_rate: float, export_traces: bool) -> None:
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
            from opentelemetry.trace import ProxyTracerProvider
        except Exception:
            logger.warning("OpenTelemetry SDK is not available; tracing is disabled", exc_info=True)
            return
        resource = Resource.create(
            {
                "service.name": self.service_name,
                "deployment.environment.name": self.environment,
                "service.version": self.service_version or "unknown",
            }
        )
        current = trace.get_tracer_provider()
        if isinstance(current, ProxyTracerProvider):
            provider = TracerProvider(resource=resource, sampler=ParentBased(TraceIdRatioBased(sample_rate)))
            trace.set_tracer_provider(provider)
            self._provider = provider
            self._owns_provider = True
        else:
            provider = current
            self._provider = None
        if export_traces and self._owns_provider:
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                from opentelemetry.sdk.trace.export import BatchSpanProcessor

                exporter = OTLPSpanExporter(
                    endpoint=f"{self.endpoint}/v1/traces",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=self.timeout,
                )
                provider.add_span_processor(BatchSpanProcessor(exporter))
            except Exception:
                logger.warning("OTLP trace exporter was not configured", exc_info=True)
        self._tracer = trace.get_tracer("observability_client")

    def _current_context(self) -> tuple[str | None, str | None]:
        span = self._active_span()
        if span is None:
            return None, None
        context = span.get_span_context()
        if not context or not context.is_valid:
            return None, None
        return f"{context.trace_id:032x}", f"{context.span_id:016x}"

    def _active_span(self) -> Any:
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
        except Exception:
            return None
        context = span.get_span_context() if span is not None else None
        if context is None or not context.is_valid:
            return None
        return span
