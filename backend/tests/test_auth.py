def test_api_key_is_hashed_and_revocable(client, admin, project):
    created = client.post(
        "/api/v1/api-keys",
        headers=admin,
        json={"name": "ci", "project_id": project["id"]},
    )
    secret = created.json()["secret"]
    assert secret.startswith("op_")
    assert "secret" not in client.get("/api/v1/api-keys", headers=admin, params={"project_id": project["id"]}).json()[0]
    from app.core.security import hash_api_key
    from app.db.session import get_session
    from app.models import ApiKey
    from sqlalchemy import select

    db = get_session()
    row = db.scalar(select(ApiKey).where(ApiKey.id == created.json()["id"]))
    assert row.key_hash == hash_api_key(secret)
    assert secret not in row.key_hash
    db.close()

    revoked = client.delete(f"/api/v1/api-keys/{created.json()['id']}", headers=admin)
    assert revoked.status_code == 200
    rejected = client.post(
        "/api/v1/logs",
        headers={"Authorization": f"Bearer {secret}"},
        json={"message": "after revoke", "severity": "INFO"},
    )
    assert rejected.status_code == 401


def test_project_isolation(client, admin):
    first = client.post("/api/v1/projects", headers=admin, json={"name": "One", "slug": "one"}).json()
    second = client.post("/api/v1/projects", headers=admin, json={"name": "Two", "slug": "two"}).json()
    key_one = client.post("/api/v1/api-keys", headers=admin, json={"name": "k", "project_id": first["id"]}).json()
    key_two = client.post("/api/v1/api-keys", headers=admin, json={"name": "k", "project_id": second["id"]}).json()
    created = client.post(
        "/api/v1/logs",
        headers={"Authorization": f"Bearer {key_one['secret']}"},
        json={"message": "only one", "severity": "INFO", "project_id": second["id"]},
    )
    assert created.status_code == 201
    assert created.json()["project_id"] == first["id"]
    other = client.get("/api/v1/logs", headers={"Authorization": f"Bearer {key_two['secret']}"})
    assert other.status_code == 200
    assert other.json()["total"] == 0
    own = client.get(
        "/api/v1/logs",
        headers={**admin, "X-Project-Id": first["id"]},
    )
    assert own.json()["total"] == 1
    missing = client.get("/api/v1/logs", headers=admin)
    assert missing.status_code == 400


def test_ingest_rejects_admin_token(client, admin):
    response = client.post(
        "/api/v1/logs",
        headers=admin,
        json={"message": "no", "severity": "INFO"},
    )
    assert response.status_code == 403


def test_ready_without_redis(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"
    assert response.json()["redis"] == "degraded"
    assert client.get("/health").json()["status"] == "ok"
