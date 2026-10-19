import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/pytest-placeholder.db")
os.environ.setdefault("REDIS_URL", "disabled")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-32-bytes-minimum")
os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "test-password-123")
os.environ.setdefault("DEV_BOOTSTRAP", "false")
os.environ.setdefault("COLLECTOR_INGEST_TOKEN", "")
os.environ.setdefault("OTLP_GRPC_ENABLED", "false")
os.environ.setdefault("ENVIRONMENT", "development")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("REDIS_URL", "disabled")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-with-32-bytes-minimum")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "test-password-123")
    monkeypatch.setenv("DEV_BOOTSTRAP", "false")
    monkeypatch.setenv("COLLECTOR_INGEST_TOKEN", "")
    monkeypatch.setenv("OTLP_GRPC_ENABLED", "false")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1000")
    monkeypatch.setenv("LOGIN_RATE_LIMIT_PER_MINUTE", "1000")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.db.session import dispose_engine
    from app.services.redis_client import init_redis, reset_memory_limiter

    dispose_engine()
    init_redis("disabled")
    reset_memory_limiter()
    from app.db.base import Base
    from app.db.session import init_engine
    import app.models  # noqa: F401

    bound = init_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bound)
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    dispose_engine()
    get_settings.cache_clear()
    reset_memory_limiter()


@pytest.fixture()
def admin(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-password-123"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def project(client, admin):
    response = client.post("/api/v1/projects", headers=admin, json={"name": "Payments", "slug": "payments"})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def reader(admin, project):
    return {**admin, "X-Project-Id": project["id"]}


@pytest.fixture()
def api_key(client, admin, project):
    response = client.post(
        "/api/v1/api-keys",
        headers=admin,
        json={"name": "ingest", "project_id": project["id"]},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    body["headers"] = {"Authorization": f"Bearer {body['secret']}"}
    return body
