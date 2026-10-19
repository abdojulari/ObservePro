from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.dependencies import AdminUser, DbSession
from app.schemas.projects import LoginIn, TokenOut, UserOut
from app.services.identity import IdentityService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut, summary="Exchange admin credentials for a bearer token")
def login(body: LoginIn, request: Request, db: DbSession) -> dict:
    host = request.client.host if request.client else "unknown"
    return IdentityService(db).login(body.email, body.password, host)


@router.get("/me", response_model=UserOut, summary="Return the authenticated administrator")
def me(admin: AdminUser) -> UserOut:
    return UserOut(id=admin.id, email=admin.email, role=admin.role)
