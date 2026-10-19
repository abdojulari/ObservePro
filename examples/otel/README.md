# OpenTelemetry export without the Python SDK

Point any OpenTelemetry SDK at the collector, which is the preferred path:

```
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
```

The collector forwards traces, metrics, and logs to the API with the
`COLLECTOR_INGEST_TOKEN`. That token is scoped to the bootstrap project.

To skip the collector, export OTLP/HTTP directly:

```
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8000
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer YOUR_PROJECT_API_KEY
```

Direct OTLP/gRPC, when enabled, listens on port 4319 so it does not collide
with the collector on 4317.
