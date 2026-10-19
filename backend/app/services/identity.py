from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import compare_digest
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    utcnow,
    verify_password,
)
from app.models import ApiKey, Project, User
from app.services.ingestion import bump
from app.services.redis_client import allow

logger = logging.getLogger(__name__)

_SLUG = re.compile(r"[^a-z0-9]+")


@dataclass
class AuthContext:
    kind: str
    project_id: str | None = None
    user: User | None = None
    api_key_id: str | None = None
    role: str | None = None


def slugify(value: str) -> str:
    slug = _SLUG.sub("-", value.strip().lower()).strip("-")
    return slug[:200] or "project"


class IdentityService:
    def __init__(self, db: Session):
        self.db = db

    def seed_admin(self, settings: Settings) -> None:
        email = settings.admin_email.strip().lower()
        existing = self.db.scalar(select(User).where(User.email == email))
        if existing is not None:
            return
        self.db.add(User(email=email, password_hash=hash_password(settings.admin_password), role="admin"))
        self.db.commit()
        logger.info("admin user created", extra={"email": email})

    def bootstrap_dev_project(self, settings: Settings) -> None:
        if not settings.dev_bootstrap:
            return
        project = self.db.scalar(select(Project).where(Project.slug == settings.dev_project_slug))
        if project is None:
            project = Project(
                name="Default",
                slug=settings.dev_project_slug,
                description="Local project created by DEV_BOOTSTRAP",
            )
            self.db.add(project)
            self.db.flush()
        active_keys = self.db.scalar(
            select(func.count())
            .select_from(ApiKey)
            .where(ApiKey.project_id == project.id, ApiKey.revoked_at.is_(None))
        )
        if not active_keys:
            secret, prefix, digest = generate_api_key()
            self.db.add(ApiKey(project_id=project.id, name="dev-bootstrap", key_prefix=prefix, key_hash=digest))
            self._write_dev_key(settings.dev_api_key_file, secret)
        self.db.commit()

    def login(self, email: str, password: str, client_host: str) -> dict:
        settings = get_settings()
        allowed, _remaining = allow(f"login:{client_host}", settings.login_rate_limit_per_minute)
        if not allowed:
            bump(self.db, "logins_rate_limited")
            raise HTTPException(status_code=429, detail="Too many login attempts", headers={"Retry-After": "60"})
        user = self.db.scalar(select(User).where(User.email == email.strip().lower()))
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        token = create_access_token(user_id=user.id, email=user.email, role=user.role)
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": settings.jwt_ttl_hours * 3600,
            "email": user.email,
            "role": user.role,
        }

    def create_project(self, name: str, slug: str | None, description: str | None) -> Project:
        chosen = slug or slugify(name)
        if self.db.scalar(select(Project).where(Project.slug == chosen)):
            raise HTTPException(status_code=409, detail="A project with that slug already exists")
        project = Project(name=name.strip(), slug=chosen, description=description)
        self.db.add(project)
        self.db.flush()
        return project

    def list_projects(self) -> list[Project]:
        return list(self.db.scalars(select(Project).order_by(Project.created_at.asc())).all())

    def create_api_key(self, project_id: str, name: str) -> tuple[ApiKey, str]:
        project = self.db.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        secret, prefix, digest = generate_api_key()
        row = ApiKey(project_id=project.id, name=name.strip(), key_prefix=prefix, key_hash=digest)
        self.db.add(row)
        self.db.flush()
        return row, secret

    def list_api_keys(self, project_id: str | None = None) -> list[ApiKey]:
        stmt = select(ApiKey).order_by(ApiKey.created_at.desc())
        if project_id:
            stmt = stmt.where(ApiKey.project_id == project_id)
        return list(self.db.scalars(stmt).all())

    def revoke_api_key(self, key_id: str) -> ApiKey:
        row = self.db.get(ApiKey, key_id)
        if row is None:
            raise HTTPException(status_code=404, detail="API key not found")
        if row.revoked_at is None:
            row.revoked_at = utcnow()
        return row

    def resolve_token(self, token: str, project_header: str | None) -> AuthContext:
        settings = get_settings()
        if token.startswith("op_"):
            return self._resolve_api_key(token, settings)
        if settings.collector_token_active() and compare_digest(token, settings.collector_ingest_token):
            return self._resolve_collector(settings)
        return self._resolve_user(token, project_header)

    def _resolve_api_key(self, token: str, settings: Settings) -> AuthContext:
        row = self.db.scalar(
            select(ApiKey).where(ApiKey.key_hash == hash_api_key(token), ApiKey.revoked_at.is_(None))
        )
        if row is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        now = utcnow()
        if row.last_used_at is None or (now - row.last_used_at).total_seconds() >= 60:
            row.last_used_at = now
        allowed, _remaining = allow(f"key:{row.id}", settings.rate_limit_per_minute)
        if not allowed:
            bump(self.db, "rate_limited")
            raise HTTPException(status_code=429, detail="Rate limit exceeded", headers={"Retry-After": "60"})
        return AuthContext(kind="api_key", project_id=row.project_id, api_key_id=row.id)

    def _resolve_collector(self, settings: Settings) -> AuthContext:
        project = self.db.scalar(select(Project).where(Project.slug == settings.dev_project_slug))
        if project is None:
            project = self.db.scalar(select(Project).order_by(Project.created_at.asc()))
        if project is None:
            raise HTTPException(status_code=401, detail="Collector token is configured but no project exists")
        allowed, _remaining = allow("collector", settings.rate_limit_per_minute)
        if not allowed:
            bump(self.db, "rate_limited")
            raise HTTPException(status_code=429, detail="Rate limit exceeded", headers={"Retry-After": "60"})
        return AuthContext(kind="collector", project_id=project.id)

    def _resolve_user(self, token: str, project_header: str | None) -> AuthContext:
        try:
            payload = decode_access_token(token)
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Invalid credentials") from exc
        user = self.db.get(User, payload.get("sub"))
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return AuthContext(kind="user", project_id=project_header, user=user, role=user.role)

    def require_project(self, ctx: AuthContext) -> str:
        if ctx.kind in {"api_key", "collector"}:
            if not ctx.project_id:
                raise HTTPException(status_code=401, detail="Invalid credentials")
            return ctx.project_id
        if ctx.role not in {"admin", "viewer"}:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        if not ctx.project_id:
            raise HTTPException(status_code=400, detail="X-Project-Id header is required")
        project = self.db.get(Project, ctx.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return project.id

    def require_admin(self, ctx: AuthContext) -> User:
        if ctx.kind != "user" or ctx.user is None or ctx.role != "admin":
            raise HTTPException(status_code=403, detail="Admin credentials are required")
        return ctx.user

    def require_ingest(self, ctx: AuthContext) -> str:
        if ctx.kind not in {"api_key", "collector"} or not ctx.project_id:
            raise HTTPException(status_code=403, detail="Ingestion requires a project API key")
        return ctx.project_id

    @staticmethod
    def _write_dev_key(path: str, secret: str) -> None:
        if not path:
            return
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(secret)
        try:
            os.chmod(path, 0o600)
        except OSError:
            logger.warning("could not restrict permissions on the dev API key file")
        logger.info("dev API key written", extra={"path": path})
