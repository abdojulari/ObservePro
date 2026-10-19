"""Read API for stored telemetry.

Routes depend on this facade. The SQL lives in ``TelemetryRepository`` so a
PostgreSQL or ClickHouse implementation can replace that class without
changing API handlers.
"""

from app.repositories.telemetry import TelemetryRepository


class QueryService(TelemetryRepository):
    pass
