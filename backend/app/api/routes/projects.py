from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.dependencies import AdminUser, DbSession, ProjectId
from app.core.config import get_settings
from app.db.session import check_database
from app.models import Project
from app.schemas.common import PlatformStatus
from app.schemas.projects import ApiKeyCreated, ApiKeyIn, ApiKeyOut, ProjectIn, ProjectOut
from app.schemas.telemetry import LogIn
from app.services.identity import IdentityService
from app.services.ingestion import IngestError, IngestionService
from app.services.redis_client import redis_state

router = APIRouter(prefix="/api/v1", tags=["projects"])

LIMITATIONS = [
    "SQLite is the initial storage backend and is appropriate for local development and small-to-medium deployments.",
    "It is not an unlimited telemetry store. High-volume production traffic should move operational data to PostgreSQL and logs, traces, and metrics to an analytical store such as ClickHouse.",
    "Ingestion is at-least-once. Idempotency-Key deduplicates retries for 24 hours; without that header a retry can create a duplicate log.",
    "Span latency percentiles are computed from at most the configured sample cap and are marked approximate beyond it. Histogram percentiles are estimated from bucket bounds and are not averages of percentiles.",
    "Do not run multiple API replicas against one SQLite file.",
]


def _project(row: Project) -> ProjectOut:
    return ProjectOut(
        id=row.id,
        name=row.name,
        slug=row.slug,
        description=row.description,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/platform", response_model=PlatformStatus, summary="Runtime limits and storage backend")
def platform(admin: AdminUser) -> PlatformStatus:
    settings = get_settings()
    state = redis_state()
    return PlatformStatus(
        version=settings.app_version,
        environment=settings.environment,
        retention_days=settings.retention_days,
        rate_limit_per_minute=settings.rate_limit_per_minute,
        max_body_bytes=settings.max_body_bytes,
        redis=state if state != "unconfigured" else "degraded",
        database="ok" if check_database() else "down",
        otlp_grpc_enabled=settings.otlp_grpc_enabled,
        limitations=LIMITATIONS,
    )


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(admin: AdminUser, db: DbSession) -> list[ProjectOut]:
    return [_project(row) for row in IdentityService(db).list_projects()]


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectIn, admin: AdminUser, db: DbSession) -> ProjectOut:
    return _project(IdentityService(db).create_project(body.name, body.slug, body.description))


@router.get("/api-keys", response_model=list[ApiKeyOut])
def list_api_keys(
    admin: AdminUser,
    db: DbSession,
    project_id: str | None = Query(default=None),
) -> list[ApiKeyOut]:
    return [_key(row) for row in IdentityService(db).list_api_keys(project_id)]


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
def create_api_key(body: ApiKeyIn, admin: AdminUser, db: DbSession) -> ApiKeyCreated:
    row, secret = IdentityService(db).create_api_key(body.project_id, body.name)
    created = ApiKeyCreated(**_key(row).model_dump(), secret=secret)
    return created


@router.delete("/api-keys/{key_id}", response_model=ApiKeyOut)
def revoke_api_key(key_id: str, admin: AdminUser, db: DbSession) -> ApiKeyOut:
    return _key(IdentityService(db).revoke_api_key(key_id))


@router.post("/projects/{project_id}/test-log", status_code=201)
def send_test_log(project_id: str, admin: AdminUser, db: DbSession):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        outcome = IngestionService(db).ingest_logs(
            project_id,
            [
                LogIn(
                    severity="INFO",
                    message="ObservePro test event",
                    service="observepro-dashboard",
                    environment="development",
                    attributes={"source": "first-run"},
                )
            ],
        )
    except IngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not outcome.logs:
        raise HTTPException(status_code=422, detail=outcome.errors)
    return outcome.logs[0]


def _key(row) -> ApiKeyOut:
    return ApiKeyOut(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        key_prefix=row.key_prefix,
        created_at=row.created_at,
        revoked_at=row.revoked_at,
        last_used_at=row.last_used_at,
    )
