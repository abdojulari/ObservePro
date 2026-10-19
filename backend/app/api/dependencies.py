from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models import User
from app.services.identity import AuthContext, IdentityService

bearer_scheme = HTTPBearer(auto_error=False)


def get_db():
    db = get_session()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_auth(
    db: DbSession,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_project_id: Annotated[str | None, Header()] = None,
) -> AuthContext:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing credentials")
    return IdentityService(db).resolve_token(credentials.credentials, x_project_id)


Auth = Annotated[AuthContext, Depends(get_auth)]


def require_admin(auth: Auth, db: DbSession) -> User:
    return IdentityService(db).require_admin(auth)


def require_project(auth: Auth, db: DbSession) -> str:
    return IdentityService(db).require_project(auth)


def require_ingest(auth: Auth, db: DbSession) -> str:
    return IdentityService(db).require_ingest(auth)


AdminUser = Annotated[User, Depends(require_admin)]
ProjectId = Annotated[str, Depends(require_project)]
IngestProjectId = Annotated[str, Depends(require_ingest)]
