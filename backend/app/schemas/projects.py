from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    email: str
    role: str


class UserOut(BaseModel):
    id: str
    email: str
    role: str


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=200, pattern=r"^[a-z0-9][a-z0-9-]{0,198}$")
    description: str | None = Field(default=None, max_length=4000)


class ProjectOut(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class ApiKeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    project_id: str = Field(min_length=1, max_length=36)


class ApiKeyOut(BaseModel):
    id: str
    project_id: str
    name: str
    key_prefix: str
    created_at: datetime
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None


class ApiKeyCreated(ApiKeyOut):
    secret: str
