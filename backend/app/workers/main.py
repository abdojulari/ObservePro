from __future__ import annotations

import logging
import time

from app.alerting.engine import AlertService
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import init_engine, session_scope
from app.services.redis_client import acquire_lock, init_redis
from app.services.retention import run_retention

logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    init_engine(settings.database_url)
    init_redis(settings.redis_url)
    logger.info("alert worker started", extra={"interval": settings.worker_interval_seconds})
    last_retention = 0.0
    while True:
        started = time.monotonic()
        if not acquire_lock("alert-worker", max(5, settings.worker_interval_seconds)):
            time.sleep(1)
            continue
        try:
            with session_scope() as db:
                AlertService(db).evaluate_all()
            with session_scope() as db:
                AlertService(db).deliver_pending()
            if time.monotonic() - last_retention >= settings.retention_interval_seconds:
                with session_scope() as db:
                    run_retention(db)
                last_retention = time.monotonic()
        except Exception:
            logger.exception("worker iteration failed")
        remaining = settings.worker_interval_seconds - (time.monotonic() - started)
        time.sleep(max(0.5, remaining))


if __name__ == "__main__":
    main()
