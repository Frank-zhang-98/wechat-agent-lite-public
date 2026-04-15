from __future__ import annotations

import atexit
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import CONFIG


class Base(DeclarativeBase):
    pass


engine = create_engine(
    f"sqlite:///{CONFIG.db_path}",
    future=True,
    connect_args={"timeout": 30, "check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=30000;")
    finally:
        cursor.close()


def ensure_runtime_indexes() -> None:
    statements = [
        "CREATE INDEX IF NOT EXISTS idx_llm_calls_created_at ON llm_calls (created_at);",
        "CREATE INDEX IF NOT EXISTS idx_llm_calls_model_created_at ON llm_calls (model, created_at);",
        "CREATE INDEX IF NOT EXISTS idx_run_steps_run_id_id ON run_steps (run_id, id);",
        "CREATE INDEX IF NOT EXISTS idx_runs_started_at_id ON runs (started_at, id);",
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.exec_driver_sql(statement)


def _dispose_engine() -> None:
    try:
        engine.dispose()
    except Exception:
        pass


atexit.register(_dispose_engine)


@contextmanager
def get_session() -> Session:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_read_session() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
