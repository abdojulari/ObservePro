def test_alembic_upgrade_creates_tables(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    config = Config("alembic.ini")
    command.upgrade(config, "head")
    names = set(inspect(create_engine(url)).get_table_names())
    assert {"projects", "api_keys", "logs", "spans", "metric_samples", "alert_incidents", "events"} <= names
