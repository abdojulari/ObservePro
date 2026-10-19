"""Explicit demo telemetry generator.

Run with `python -m app.demo`. This is separate from normal ingestion and is
never invoked by the API process.
"""

from __future__ import annotations

import random
from datetime import timedelta

from app.alerting.engine import AlertService
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.security import utcnow
from app.db.session import init_engine, session_scope
from app.schemas.alerts import AlertIn, AlertRuleIn
from app.schemas.telemetry import EventIn, LogIn, MetricIn
from app.services.identity import IdentityService
from app.services.ingestion import IngestionService
from app.telemetry.otlp import IncomingSpan


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    init_engine(settings.database_url)
    now = utcnow()
    with session_scope() as db:
        identity = IdentityService(db)
        identity.seed_admin(settings)
        project = identity.create_project("Demo", f"demo-{int(now.timestamp())}", "Generated demo telemetry")
        _key, secret = identity.create_api_key(project.id, "demo")
        ingest = IngestionService(db)
        services = ["checkout", "payments", "inventory"]
        for offset in range(40):
            moment = now - timedelta(minutes=40 - offset)
            service = services[offset % len(services)]
            severity = "ERROR" if offset % 9 == 0 else "WARN" if offset % 5 == 0 else "INFO"
            ingest.ingest_logs(
                project.id,
                [
                    LogIn(
                        timestamp=moment,
                        severity=severity,
                        message="Payment provider timed out" if severity == "ERROR" else f"{service} handled a request",
                        service=service,
                        environment="demo",
                        trace_id=f"{offset:032x}",
                        attributes={"order_id": f"order-{offset}"},
                    )
                ],
            )
            start = moment
            end = moment + timedelta(milliseconds=80 + offset)
            ingest.ingest_spans(
                project.id,
                [
                    IncomingSpan(
                        trace_id=f"{offset:032x}",
                        span_id=f"{offset:016x}",
                        parent_span_id=None,
                        name="POST /checkout",
                        kind="server",
                        start_time=start,
                        end_time=end,
                        status_code="error" if severity == "ERROR" else "ok",
                        status_message=None,
                        service=service,
                        environment="demo",
                        version="1.0.0",
                        attributes={"http.request.method": "POST"},
                    )
                ],
            )
            ingest.ingest_metrics(
                project.id,
                [
                    MetricIn(
                        name="http.server.duration",
                        type="histogram",
                        timestamp=moment,
                        service=service,
                        environment="demo",
                        unit="ms",
                        value=float(50 + offset),
                    )
                ],
            )
        ingest.ingest_events(
            project.id,
            [EventIn(name="deployment", message="demo release", service="checkout", environment="demo")],
        )
        alerts = AlertService(db)
        alerts.create_rule(
            project.id,
            AlertRuleIn(
                name="Demo error count",
                condition_type="error_count",
                threshold=1,
                window_seconds=3600,
                severity="HIGH",
                environment="demo",
            ),
        )
        alerts.evaluate_all()
        alerts.submit_external(
            project.id,
            AlertIn(title="Demo external alert", message="Submitted by the demo generator", severity="MEDIUM", service="payments"),
        )
    print("Demo project created.")
    print(f"API key (shown once): {secret}")
    print("Sign in to the dashboard and select the new demo project.")


if __name__ == "__main__":
    main()
