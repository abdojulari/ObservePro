# Universal Observability Platform

ObservePro is a self-hosted observability server. Applications send logs, events, and alerts over HTTP, and traces, metrics, and logs over OTLP. A React dashboard searches and charts what was stored. The Python SDK is optional. Any language can use the HTTP API or a standard OpenTelemetry exporter.

SQLite is the storage backend for local and small deployments. It is not an unlimited telemetry database.

## Start locally

```bash
cp .env.example .env
docker compose up --build
```

Change `SECRET_KEY`, `ADMIN_PASSWORD`, and `COLLECTOR_INGEST_TOKEN` before sharing the deployment. The published defaults are rejected as collector credentials when `ENVIRONMENT=production`.

- Dashboard: http://localhost:5173
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Readiness: http://localhost:8000/ready

Sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD` (`admin@localhost` / `changeme` unless you changed them). Create a project, generate an API key, and use **Send test log**. The raw key is shown once. Only its SHA-256 hash is stored.

With `DEV_BOOTSTRAP=true`, Compose also creates a project named `default` and writes one API key to `/data/dev_api_key` inside the `observe-data` volume. The key is not printed in logs.

```bash
docker compose exec backend cat /data/dev_api_key
```

Demo data is a separate command. It does not run on startup:

```bash
docker compose exec backend python -m app.demo
```

## Run without Docker

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt
cd backend
.venv/bin/alembic upgrade head
REDIS_URL=disabled .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another shell, from `frontend/`:

```bash
npm install
npm run dev
```

`REDIS_URL=disabled` keeps rate limits and dashboard cache in process. `/ready` stays successful and reports Redis as degraded. Start Redis when you want shared limits, the short analytics cache, and the worker lock.

The worker evaluates alert rules and retention:

```bash
cd backend && OTLP_GRPC_ENABLED=false .venv/bin/python -m app.workers.main
```

## Authentication

| Credential | What it can do |
| --- | --- |
| Admin JWT from `POST /api/v1/auth/login` | Projects, API keys, rules, channels, dashboard reads. Send `X-Project-Id` on project-scoped reads. |
| Project API key `Authorization: Bearer op_...` | Ingest and read that project only. A `project_id` in the body is ignored. |
| `COLLECTOR_INGEST_TOKEN` | OTLP ingest for the bootstrap project. Not an admin credential. |

Revoke a key with `DELETE /api/v1/api-keys/{key_id}`. Create a new one to rotate. Login and ingestion are rate limited.

## HTTP API

Interactive schemas are at `/docs`.

Ingestion returns `201` for one record and `200` with `{accepted, rejected, errors, ids}` when a batch is partially valid. A body that fails schema validation returns `422` for the whole request. `Idempotency-Key` replays the stored response for 24 hours. The same key with a different body returns `409`. Delivery is at-least-once. A retry without that header can duplicate a log. Span identity `(project, trace_id, span_id)` is upserted. Cumulative metric points at the same timestamp and series are upserted. Delta metric retries can duplicate.

List endpoints use `page` and `page_size`. Time filters accept `from` and `to`, or `range` of `15m`, `1h`, `6h`, `24h`, `7d` on analytics, services, and metrics.

Log levels are `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL` (OpenTelemetry severity numbers 1, 5, 9, 13, 17, 21). `WARNING` maps to `WARN` and `CRITICAL` maps to `FATAL`.

Alert severities are `INFO`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`, `EMERGENCY`, mapped to OpenTelemetry INFO/9, INFO/10, WARN/13, ERROR/17, FATAL/21, and FATAL/24.

```bash
OBSERVE_API_KEY=op_... sh examples/curl/send-log.sh
OBSERVE_API_KEY=op_... sh examples/curl/send-alert.sh
OBSERVE_API_KEY=op_... node examples/node/send-telemetry.mjs
```

## OpenTelemetry

The collector is the preferred ingestion path. `collector/otel-collector-config.yaml` receives OTLP on 4317 (gRPC) and 4318 (HTTP) and exports to the API.

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
```

Direct OTLP/HTTP is `POST /v1/traces`, `/v1/metrics`, and `/v1/logs` with a project API key. Optional OTLP/gRPC listens on 4319 when `OTLP_GRPC_ENABLED=true`. JSON and protobuf are both accepted. Histogram percentiles are computed from bucket bounds. They are not averages of percentile values. Span P50/P95/P99 use a capped sample (`latency_sample_cap`, default 20000) and are marked approximate past that cap.

Logs that include a trace ID show up on the trace detail page.

## Python SDK

```bash
pip install -e ./sdk/python
```

```python
from observability_client import ObservabilityClient

client = ObservabilityClient(
    endpoint="http://localhost:8000",
    api_key="YOUR_PROJECT_API_KEY",
    service_name="payment-service",
    environment="development",
)
client.info("Payment service started")
client.flush()
client.shutdown()
```

Tracing uses the OpenTelemetry SDK. If the process does not already have a tracer provider, the client installs one and can export spans to `{endpoint}/v1/traces`. Logs are queued on a background thread. A full buffer drops the new event when `fail_open=True` (the default) and raises `BufferFull` otherwise. Timeouts and retries stay bounded. Transport failures are not reported back through the same client.

`examples/python-fastapi` shows FastAPI instrumentation. `examples/python-script` is a one-shot sender. `sdk/python/examples/basic.py` matches the full client surface.

## Alerts

Rules are evaluated by the worker, not on each ingest. Conditions: `error_count`, `error_rate`, `p95_latency`, `metric_threshold`, `service_silence`, `log_severity`, `event_match`. Each rule has a window, comparison, threshold, severity, optional service or environment, and a cooldown.

Lifecycle is `PENDING → FIRING → ACKNOWLEDGED → RESOLVED`. The same unresolved fingerprint updates the open incident instead of opening another one. A resolved incident can open again after the cooldown. With no notification channel, an incident is stored as `FIRING` immediately. A webhook channel keeps it `PENDING` until delivery finishes. Webhook attempts are bounded. In production, webhook URLs must not target private or link-local hosts. Localhost is allowed in development.

## Storage and scale

SQLite uses WAL, foreign keys, a busy timeout, and short transactions. Retention deletes old telemetry in batches. Open alerts are kept. Do not point more than one API process at the same SQLite file. Redis is a cache and coordination layer, not the only copy of telemetry.

Move operational records to PostgreSQL and high-volume logs, traces, and metrics to an analytical store such as ClickHouse when this file is no longer enough. Repositories sit between the API and SQLite so that change does not rewrite the routes.

## Security

The repository contains no personal data and no production secrets. The only credentials in source are local placeholders (`admin@localhost`, `changeme`, `dev-only-change-me`, `dev-only-collector-token`) and test values such as `admin@example.com`. Passwords and API keys are stored as hashes. A raw API key is returned once at creation and is not written to logs.

Admin login does not dump data. `POST /api/v1/auth/login` checks the password and returns a JWT, the admin email, and the role. The request log records method, path, and status code. It does not record the password, the token, the authorization header, or any telemetry. Reading logs, traces, metrics, and alerts is a separate request after sign-in, limited to the selected project.

Telemetry sent to the platform can still contain personal or confidential data. Keep the dashboard behind the admin login, scope API keys to projects, and set `RETENTION_DAYS`. Attribute keys such as `password`, `secret`, `token`, `api_key`, and `authorization` are redacted. Request bodies are size limited. CORS allows only `CORS_ORIGINS`.

## Tests

```bash
make test-backend
make test-sdk
make test-frontend
```

Backend coverage includes ingestion, isolation, OTLP protobuf, alert lifecycle, retention, rate limits, and Redis being down. The end-to-end test creates a project, sends a log, a trace, a metric, and an alert, then reads them back through the same APIs the dashboard uses.

## Todo

Areas still worth improving. The items below are not implemented.

### Storage and deployment

- [ ] Add a PostgreSQL repository for projects, API keys, alert rules, and incidents.
- [ ] Add an analytical store such as ClickHouse for logs, spans, and metric samples.
- [ ] Run and document a clean `docker compose up --build` check in CI.
- [ ] Add a production reverse-proxy example with TLS in front of the API and dashboard.
- [ ] Publish the Python SDK to a package index. Today it is installed from this repository.

### Ingestion and OpenTelemetry

- [ ] Add an automated test for the optional OTLP/gRPC receiver on port 4319.
- [ ] Let each project use its own collector credential. The shared collector token writes only to the bootstrap project.
- [ ] Make delta metric retries idempotent. Cumulative points and spans already upsert; delta retries can still duplicate.
- [ ] Add a full-text index for log search. Filtering currently uses SQL predicates and pagination.

### Alerting and administration

- [ ] Add notification channels beyond webhook, such as email and Slack.
- [ ] Edit an existing alert rule in the dashboard. The API accepts `PUT`; the UI creates and deletes rules.
- [ ] Update the admin password after the first seed. Changing `ADMIN_PASSWORD` later does not replace the stored hash.
- [ ] Add more than one administrator, with roles for read-only dashboard access and project administration.
- [ ] Expose per-project retention in the dashboard. Retention is a single platform setting today.

### Dashboard

- [ ] Add a page for custom events. `POST /api/v1/events` stores them, and the UI does not list them.
- [ ] Split the frontend bundle. The production build is one chunk larger than 500 kB.
- [ ] Expose log table rows to assistive technology. The row text is visible, and the accessibility tree does not name each cell.
- [ ] Exercise a live trace waterfall and alert acknowledgement in the browser. Those flows are covered by API and component tests.

### Verification

- [ ] Add a CI workflow that runs backend, SDK, and frontend tests on every change.
- [ ] Keep a single worker when Redis is down. Without the lock, two workers can evaluate the same rule; the open-fingerprint unique index prevents a duplicate open incident.

## Troubleshooting

- `/ready` reports Redis degraded: the API is up and using in-process limits. Start Redis for shared coordination.
- Dashboard login fails: confirm `ADMIN_EMAIL` and `ADMIN_PASSWORD`. Changing the password later does not update an admin that was already created.
- Empty charts: the time range may not cover the data. Demo and test logs use the current time. A curl example with a fixed timestamp can fall outside `15m`.
- Collector exports are rejected: the token must match `COLLECTOR_INGEST_TOKEN`, and that token only writes to the bootstrap project.
- SQLite `database is locked`: keep a single API process and the worker. Do not add API replicas on one file.

## License

MIT License

Copyright (c) 2026 ObservePro Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
