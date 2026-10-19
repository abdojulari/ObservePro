from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.security import utcnow
from app.schemas.telemetry import EventIn, LogIn, MetricIn
from app.telemetry.severity import number_to_text

logger = logging.getLogger(__name__)

_KIND = {
    0: "unspecified",
    1: "internal",
    2: "server",
    3: "client",
    4: "producer",
    5: "consumer",
    "SPAN_KIND_UNSPECIFIED": "unspecified",
    "SPAN_KIND_INTERNAL": "internal",
    "SPAN_KIND_SERVER": "server",
    "SPAN_KIND_CLIENT": "client",
    "SPAN_KIND_PRODUCER": "producer",
    "SPAN_KIND_CONSUMER": "consumer",
}
_STATUS = {
    0: "unset",
    1: "ok",
    2: "error",
    "STATUS_CODE_UNSET": "unset",
    "STATUS_CODE_OK": "ok",
    "STATUS_CODE_ERROR": "error",
}


@dataclass
class IncomingSpan:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    kind: str
    start_time: datetime
    end_time: datetime
    status_code: str
    status_message: str | None
    service: str
    environment: str | None
    version: str | None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    links: list[dict[str, Any]] = field(default_factory=list)
    resource_attributes: dict[str, Any] = field(default_factory=dict)


def decode_id(value: Any, nbytes: int) -> str:
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    text = str(value).strip()
    hex_len = nbytes * 2
    if len(text) == hex_len and all(char in "0123456789abcdefABCDEF" for char in text):
        return text.lower()
    try:
        padded = text + "=" * (-len(text) % 4)
        raw = base64.b64decode(padded, validate=True)
        if raw:
            return raw.hex()
    except Exception:
        pass
    return text.replace("-", "").lower()[: hex_len or 64]


def nano_to_datetime(value: Any) -> datetime:
    if value in (None, "", 0, "0"):
        return utcnow()
    nanos = int(value)
    return datetime.fromtimestamp(nanos / 1_000_000_000, tz=timezone.utc)


def _json_any(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        try:
            return int(value["intValue"])
        except (TypeError, ValueError):
            return value["intValue"]
    if "doubleValue" in value:
        return value["doubleValue"]
    if "boolValue" in value:
        return value["boolValue"]
    if "bytesValue" in value:
        return value["bytesValue"]
    if "arrayValue" in value:
        return [_json_any(item) for item in value.get("arrayValue", {}).get("values", [])]
    if "kvlistValue" in value:
        return {
            item.get("key"): _json_any(item.get("value"))
            for item in value.get("kvlistValue", {}).get("values", [])
        }
    return None


def _json_attrs(values: Any) -> dict[str, Any]:
    if isinstance(values, dict):
        return dict(values)
    result: dict[str, Any] = {}
    for item in values or []:
        if isinstance(item, dict) and item.get("key") is not None:
            result[str(item["key"])] = _json_any(item.get("value"))
    return result


def _service_from_resource(resource: dict[str, Any]) -> tuple[str, str | None, str | None]:
    service = str(resource.get("service.name") or "unknown")
    environment = resource.get("deployment.environment.name") or resource.get("deployment.environment")
    version = resource.get("service.version")
    return service, (str(environment) if environment else None), (str(version) if version else None)


def _span_kind(value: Any) -> str:
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    return _KIND.get(value, "internal")


def _span_status(value: Any) -> str:
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    return _STATUS.get(value, "unset")


def spans_from_json(payload: dict[str, Any]) -> list[IncomingSpan]:
    spans: list[IncomingSpan] = []
    for resource_spans in payload.get("resourceSpans") or []:
        resource = _json_attrs((resource_spans.get("resource") or {}).get("attributes"))
        service, environment, version = _service_from_resource(resource)
        for scope in resource_spans.get("scopeSpans") or resource_spans.get("instrumentationLibrarySpans") or []:
            for span in scope.get("spans") or []:
                status = span.get("status") or {}
                start = nano_to_datetime(span.get("startTimeUnixNano"))
                end = nano_to_datetime(span.get("endTimeUnixNano"))
                if end < start:
                    end = start
                parent = decode_id(span.get("parentSpanId"), 8)
                spans.append(
                    IncomingSpan(
                        trace_id=decode_id(span.get("traceId"), 16),
                        span_id=decode_id(span.get("spanId"), 8),
                        parent_span_id=parent or None,
                        name=str(span.get("name") or "span"),
                        kind=_span_kind(span.get("kind", 1)),
                        start_time=start,
                        end_time=end,
                        status_code=_span_status(status.get("code", 0)),
                        status_message=status.get("message") or None,
                        service=service,
                        environment=environment,
                        version=version,
                        attributes=_json_attrs(span.get("attributes")),
                        events=[
                            {
                                "name": event.get("name"),
                                "timestamp": nano_to_datetime(event.get("timeUnixNano")).isoformat(),
                                "attributes": _json_attrs(event.get("attributes")),
                            }
                            for event in span.get("events") or []
                        ],
                        links=[
                            {
                                "trace_id": decode_id(link.get("traceId"), 16),
                                "span_id": decode_id(link.get("spanId"), 8),
                                "attributes": _json_attrs(link.get("attributes")),
                            }
                            for link in span.get("links") or []
                        ],
                        resource_attributes=resource,
                    )
                )
    return spans


def _coerce_severity(text: Any, number: Any) -> tuple[str | None, int | None]:
    aliases = {"WARNING": "WARN", "CRITICAL": "FATAL"}
    if text:
        key = aliases.get(str(text).strip().upper(), str(text).strip().upper())
        if key in {"TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"}:
            parsed = int(number) if number not in (None, "", 0) else None
            return key, parsed if parsed and parsed >= 1 else None
    if number not in (None, "", 0):
        parsed = int(number)
        if parsed >= 1:
            return number_to_text(parsed), min(24, parsed)
    return None, None


def logs_from_json(payload: dict[str, Any]) -> list[LogIn]:
    items: list[LogIn] = []
    for resource_logs in payload.get("resourceLogs") or []:
        resource = _json_attrs((resource_logs.get("resource") or {}).get("attributes"))
        service, environment, version = _service_from_resource(resource)
        for scope in resource_logs.get("scopeLogs") or resource_logs.get("instrumentationLibraryLogs") or []:
            for record in scope.get("logRecords") or []:
                body = record.get("body")
                message = _json_any(body) if isinstance(body, dict) else body
                if not isinstance(message, str):
                    message = json.dumps(message, default=str) if message is not None else ""
                if not message:
                    continue
                text, number = _coerce_severity(record.get("severityText"), record.get("severityNumber"))
                attributes = _json_attrs(record.get("attributes"))
                attributes.update({key: value for key, value in resource.items() if key not in attributes})
                timestamp = record.get("timeUnixNano") or record.get("observedTimeUnixNano")
                items.append(
                    LogIn(
                        timestamp=nano_to_datetime(timestamp) if timestamp else None,
                        severity=text,
                        severity_number=number,
                        message=message[:16384],
                        service=service,
                        environment=environment or "production",
                        version=version,
                        trace_id=decode_id(record.get("traceId"), 16) or None,
                        span_id=decode_id(record.get("spanId"), 8) or None,
                        attributes=attributes,
                    )
                )
    return items


def _histogram_from_json(point: dict[str, Any]) -> tuple[list[float] | None, list[int] | None, int | None, float | None]:
    bounds = point.get("explicitBounds")
    counts = point.get("bucketCounts")
    if bounds is None or counts is None:
        return None, None, point.get("count"), point.get("sum")
    return (
        [float(item) for item in bounds],
        [int(item) for item in counts],
        int(point.get("count") or sum(int(item) for item in counts)),
        float(point["sum"]) if point.get("sum") is not None else None,
    )


def metrics_from_json(payload: dict[str, Any]) -> list[MetricIn]:
    items: list[MetricIn] = []
    for resource_metrics in payload.get("resourceMetrics") or []:
        resource = _json_attrs((resource_metrics.get("resource") or {}).get("attributes"))
        service, environment, version = _service_from_resource(resource)
        for scope in resource_metrics.get("scopeMetrics") or resource_metrics.get("instrumentationLibraryMetrics") or []:
            for metric in scope.get("metrics") or []:
                name = str(metric.get("name") or "unknown")
                description = metric.get("description")
                unit = metric.get("unit")
                items.extend(
                    _metric_points_from_json(
                        metric,
                        name=name,
                        description=description,
                        unit=unit,
                        service=service,
                        environment=environment or "production",
                        version=version,
                    )
                )
    return items


def _number_value(point: dict[str, Any]) -> float | None:
    if "asDouble" in point:
        return float(point["asDouble"])
    if "asInt" in point:
        return float(point["asInt"])
    return None


def _metric_points_from_json(metric: dict[str, Any], **common: Any) -> list[MetricIn]:
    version = common.pop("version", None)
    produced: list[MetricIn] = []
    if "gauge" in metric:
        data = metric["gauge"]
        for point in data.get("dataPoints") or []:
            produced.append(
                MetricIn(
                    name=common["name"],
                    type="gauge",
                    timestamp=nano_to_datetime(point.get("timeUnixNano")),
                    value=_number_value(point),
                    service=common["service"],
                    environment=common["environment"],
                    unit=common["unit"],
                    description=common["description"],
                    attributes=_point_attributes(point, version),
                    temporality="delta",
                )
            )
    if "sum" in metric:
        data = metric["sum"]
        temporality = "cumulative" if data.get("aggregationTemporality") in (2, "AGGREGATION_TEMPORALITY_CUMULATIVE") else "delta"
        for point in data.get("dataPoints") or []:
            produced.append(
                MetricIn(
                    name=common["name"],
                    type="counter",
                    timestamp=nano_to_datetime(point.get("timeUnixNano")),
                    value=_number_value(point),
                    service=common["service"],
                    environment=common["environment"],
                    unit=common["unit"],
                    description=common["description"],
                    temporality=temporality,
                    is_monotonic=bool(data.get("isMonotonic", True)),
                    attributes=_point_attributes(point, version),
                )
            )
    if "histogram" in metric:
        data = metric["histogram"]
        temporality = "cumulative" if data.get("aggregationTemporality") in (2, "AGGREGATION_TEMPORALITY_CUMULATIVE") else "delta"
        for point in data.get("dataPoints") or []:
            bounds, counts, count, total = _histogram_from_json(point)
            produced.append(
                MetricIn(
                    name=common["name"],
                    type="histogram",
                    timestamp=nano_to_datetime(point.get("timeUnixNano")),
                    service=common["service"],
                    environment=common["environment"],
                    unit=common["unit"],
                    description=common["description"],
                    temporality=temporality,
                    count=count,
                    sum=total,
                    min=point.get("min"),
                    max=point.get("max"),
                    bucket_bounds=bounds,
                    bucket_counts=counts,
                    attributes=_point_attributes(point, version),
                )
            )
    if "exponentialHistogram" in metric:
        data = metric["exponentialHistogram"]
        temporality = "cumulative" if data.get("aggregationTemporality") in (2, "AGGREGATION_TEMPORALITY_CUMULATIVE") else "delta"
        for point in data.get("dataPoints") or []:
            positive = point.get("positive") or {}
            bounds, counts = _exponential_buckets(
                int(point.get("scale") or 0),
                int(positive.get("offset") or 0),
                [int(item) for item in positive.get("bucketCounts") or []],
            )
            produced.append(
                MetricIn(
                    name=common["name"],
                    type="exponential_histogram",
                    timestamp=nano_to_datetime(point.get("timeUnixNano")),
                    service=common["service"],
                    environment=common["environment"],
                    unit=common["unit"],
                    description=common["description"],
                    temporality=temporality,
                    count=int(point.get("count") or 0),
                    sum=point.get("sum"),
                    min=point.get("min"),
                    max=point.get("max"),
                    bucket_bounds=bounds or None,
                    bucket_counts=counts or None,
                    attributes=_point_attributes(point, version),
                )
            )
    return produced


def _point_attributes(point: dict[str, Any], version: str | None) -> dict[str, Any]:
    attributes = _json_attrs(point.get("attributes"))
    if version:
        attributes.setdefault("service.version", version)
    return attributes


def _exponential_buckets(scale: int, offset: int, counts: list[int]) -> tuple[list[float], list[int]]:
    if not counts:
        return [], []
    base = 2 ** (2 ** (-scale))
    bounds: list[float] = []
    bucket_counts: list[int] = []
    for index, count in enumerate(counts):
        upper = base ** (offset + index + 1)
        bounds.append(float(upper))
        bucket_counts.append(int(count))
    bucket_counts.append(0)
    return bounds, bucket_counts


def _pb_any(value: Any) -> Any:
    kind = value.WhichOneof("value")
    if kind is None:
        return None
    if kind == "array_value":
        return [_pb_any(item) for item in value.array_value.values]
    if kind == "kvlist_value":
        return {item.key: _pb_any(item.value) for item in value.kvlist_value.values}
    if kind == "bytes_value":
        return value.bytes_value.hex()
    return getattr(value, kind)


def _pb_attrs(values: Any) -> dict[str, Any]:
    return {item.key: _pb_any(item.value) for item in values}


def spans_from_protobuf(payload: bytes) -> list[IncomingSpan]:
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

    request = ExportTraceServiceRequest()
    request.ParseFromString(payload)
    return _spans_from_proto_request(request)


def _spans_from_proto_request(request: Any) -> list[IncomingSpan]:
    spans: list[IncomingSpan] = []
    for resource_spans in request.resource_spans:
        resource = _pb_attrs(resource_spans.resource.attributes)
        service, environment, version = _service_from_resource(resource)
        for scope in resource_spans.scope_spans:
            for span in scope.spans:
                start = nano_to_datetime(span.start_time_unix_nano)
                end = nano_to_datetime(span.end_time_unix_nano)
                if end < start:
                    end = start
                parent = span.parent_span_id.hex() if span.parent_span_id else None
                spans.append(
                    IncomingSpan(
                        trace_id=span.trace_id.hex(),
                        span_id=span.span_id.hex(),
                        parent_span_id=parent or None,
                        name=span.name or "span",
                        kind=_span_kind(int(span.kind)),
                        start_time=start,
                        end_time=end,
                        status_code=_span_status(int(span.status.code)),
                        status_message=span.status.message or None,
                        service=service,
                        environment=environment,
                        version=version,
                        attributes=_pb_attrs(span.attributes),
                        events=[
                            {
                                "name": event.name,
                                "timestamp": nano_to_datetime(event.time_unix_nano).isoformat(),
                                "attributes": _pb_attrs(event.attributes),
                            }
                            for event in span.events
                        ],
                        links=[
                            {
                                "trace_id": link.trace_id.hex(),
                                "span_id": link.span_id.hex(),
                                "attributes": _pb_attrs(link.attributes),
                            }
                            for link in span.links
                        ],
                        resource_attributes=resource,
                    )
                )
    return spans


def logs_from_protobuf(payload: bytes) -> list[LogIn]:
    from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest

    request = ExportLogsServiceRequest()
    request.ParseFromString(payload)
    return _logs_from_proto_request(request)


def _logs_from_proto_request(request: Any) -> list[LogIn]:
    items: list[LogIn] = []
    for resource_logs in request.resource_logs:
        resource = _pb_attrs(resource_logs.resource.attributes)
        service, environment, version = _service_from_resource(resource)
        for scope in resource_logs.scope_logs:
            for record in scope.log_records:
                message = _pb_any(record.body)
                if not isinstance(message, str):
                    message = json.dumps(message, default=str) if message is not None else ""
                if not message:
                    continue
                text, number = _coerce_severity(record.severity_text, int(record.severity_number) or None)
                attributes = _pb_attrs(record.attributes)
                timestamp = record.time_unix_nano or record.observed_time_unix_nano
                items.append(
                    LogIn(
                        timestamp=nano_to_datetime(timestamp) if timestamp else None,
                        severity=text,
                        severity_number=number,
                        message=message[:16384],
                        service=service,
                        environment=environment or "production",
                        version=version,
                        trace_id=record.trace_id.hex() or None,
                        span_id=record.span_id.hex() or None,
                        attributes=attributes,
                    )
                )
    return items


def metrics_from_protobuf(payload: bytes) -> list[MetricIn]:
    from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest

    request = ExportMetricsServiceRequest()
    request.ParseFromString(payload)
    return _metrics_from_proto_request(request)


def _metrics_from_proto_request(request: Any) -> list[MetricIn]:
    # Reuse the JSON converter by emitting a JSON-shaped document. This keeps
    # histogram and temporality handling in one place.
    document: dict[str, Any] = {"resourceMetrics": []}
    for resource_metrics in request.resource_metrics:
        resource_attributes = [
            {"key": key, "value": {"stringValue": str(value)}}
            for key, value in _pb_attrs(resource_metrics.resource.attributes).items()
        ]
        scopes = []
        for scope in resource_metrics.scope_metrics:
            metrics = []
            for metric in scope.metrics:
                metrics.append(_proto_metric_to_json(metric))
            scopes.append({"metrics": [item for item in metrics if item]})
        document["resourceMetrics"].append(
            {"resource": {"attributes": resource_attributes}, "scopeMetrics": scopes}
        )
    return metrics_from_json(document)


def _proto_metric_to_json(metric: Any) -> dict[str, Any]:
    base = {"name": metric.name, "description": metric.description, "unit": metric.unit}
    kind = metric.WhichOneof("data")
    if kind == "gauge":
        base["gauge"] = {"dataPoints": [_proto_number_point(point) for point in metric.gauge.data_points]}
    elif kind == "sum":
        base["sum"] = {
            "aggregationTemporality": int(metric.sum.aggregation_temporality),
            "isMonotonic": bool(metric.sum.is_monotonic),
            "dataPoints": [_proto_number_point(point) for point in metric.sum.data_points],
        }
    elif kind == "histogram":
        base["histogram"] = {
            "aggregationTemporality": int(metric.histogram.aggregation_temporality),
            "dataPoints": [_proto_histogram_point(point) for point in metric.histogram.data_points],
        }
    elif kind == "exponential_histogram":
        base["exponentialHistogram"] = {
            "aggregationTemporality": int(metric.exponential_histogram.aggregation_temporality),
            "dataPoints": [
                _proto_exponential_point(point) for point in metric.exponential_histogram.data_points
            ],
        }
    else:
        return {}
    return base


def _proto_number_point(point: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "timeUnixNano": str(point.time_unix_nano),
        "attributes": _attrs_to_json(_pb_attrs(point.attributes)),
    }
    value_kind = point.WhichOneof("value")
    if value_kind == "as_int":
        payload["asInt"] = str(point.as_int)
    elif value_kind == "as_double":
        payload["asDouble"] = point.as_double
    return payload


def _proto_histogram_point(point: Any) -> dict[str, Any]:
    return {
        "timeUnixNano": str(point.time_unix_nano),
        "count": int(point.count),
        "sum": point.sum if point.HasField("sum") else None,
        "min": point.min if point.HasField("min") else None,
        "max": point.max if point.HasField("max") else None,
        "bucketCounts": [int(item) for item in point.bucket_counts],
        "explicitBounds": [float(item) for item in point.explicit_bounds],
        "attributes": _attrs_to_json(_pb_attrs(point.attributes)),
    }


def _proto_exponential_point(point: Any) -> dict[str, Any]:
    positive = point.positive
    return {
        "timeUnixNano": str(point.time_unix_nano),
        "count": int(point.count),
        "sum": point.sum if point.HasField("sum") else None,
        "scale": int(point.scale),
        "positive": {
            "offset": int(positive.offset),
            "bucketCounts": [int(item) for item in positive.bucket_counts],
        },
        "attributes": _attrs_to_json(_pb_attrs(point.attributes)),
    }


def _attrs_to_json(attributes: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for key, value in attributes.items():
        if isinstance(value, bool):
            wrapped: dict[str, Any] = {"boolValue": value}
        elif isinstance(value, int):
            wrapped = {"intValue": str(value)}
        elif isinstance(value, float):
            wrapped = {"doubleValue": value}
        else:
            wrapped = {"stringValue": str(value)}
        items.append({"key": key, "value": wrapped})
    return items


def protobuf_response(signal: str, rejected: int) -> bytes:
    if signal == "traces":
        from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse

        message = ExportTraceServiceResponse()
        field_name = "rejected_spans"
    elif signal == "metrics":
        from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceResponse

        message = ExportMetricsServiceResponse()
        field_name = "rejected_data_points"
    else:
        from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceResponse

        message = ExportLogsServiceResponse()
        field_name = "rejected_log_records"
    if rejected and hasattr(message, "partial_success"):
        setattr(message.partial_success, field_name, int(rejected))
        message.partial_success.error_message = f"{rejected} item(s) were rejected"
    return message.SerializeToString()
