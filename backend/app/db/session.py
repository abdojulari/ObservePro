from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

logger = logging.getLogger(__name__)

engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def _sqlite_on_connect(dbapi_connection, _connection_record) -> None:
    # Let SQLAlchemy own transactions so SAVEPOINT release does not commit.
    dbapi_connection.isolation_level = None
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def _sqlite_on_begin(connection) -> None:
    connection.exec_driver_sql("BEGIN")


def init_engine(url: str | None = None) -> Engine:
    global engine, SessionLocal
    database_url = url or get_settings().database_url
    if engine is not None:
        engine.dispose()
    kwargs: dict = {"future": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if database_url in {"sqlite://", "sqlite:///:memory:"}:
            kwargs["poolclass"] = StaticPool
    new_engine = create_engine(database_url, **kwargs)
    if new_engine.dialect.name == "sqlite":
        event.listen(new_engine, "connect", _sqlite_on_connect)
        event.listen(new_engine, "begin", _sqlite_on_begin)
    engine = new_engine
    SessionLocal = sessionmaker(bind=engine, autoflush=True, autocommit=False, expire_on_commit=False)
    return engine


def dispose_engine() -> None:
    global engine, SessionLocal
    if engine is not None:
        engine.dispose()
    engine = None
    SessionLocal = None


def get_session() -> Session:
    if SessionLocal is None:
        init_engine()
    assert SessionLocal is not None
    return SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = get_session()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_database() -> bool:
    try:
        db = get_session()
        try:
            db.execute(text("SELECT 1"))
            return True
        finally:
            db.close()
    except Exception:
        logger.exception("database health check failed")
        return False
