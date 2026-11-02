"""Engine / session factories and the ``get_db`` FastAPI dependency."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings

SQLITE_PREFIX = "sqlite"

_ENGINES: dict[tuple[str, bool], Engine] = {}
_SESSION_MAKERS: dict[tuple[str, bool], sessionmaker[Session]] = {}


def _cache_key(settings: Settings) -> tuple[str, bool]:
    return settings.database_url, settings.sql_echo


@lru_cache(maxsize=1)
def _default_settings() -> Settings:
    return get_settings()


def get_engine(settings: Settings | None = None) -> Engine:
    """One engine per (url, echo) pair, so repeated calls share the connection pool."""
    settings = settings or _default_settings()
    key = _cache_key(settings)
    if key not in _ENGINES:
        is_sqlite = settings.database_url.startswith(SQLITE_PREFIX)
        engine = create_engine(
            settings.database_url,
            echo=settings.sql_echo,
            future=True,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False} if is_sqlite else {},
        )
        if is_sqlite:
            _enable_sqlite_pragmas(engine)
        _ENGINES[key] = engine
    return _ENGINES[key]


def _enable_sqlite_pragmas(engine: Engine) -> None:
    """WAL keeps concurrent readers from blocking the rolling writer; FKs are opt-in on SQLite."""

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _record) -> None:  # pragma: no cover - driver callback
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def get_sessionmaker(settings: Settings | None = None) -> sessionmaker[Session]:
    settings = settings or _default_settings()
    key = _cache_key(settings)
    if key not in _SESSION_MAKERS:
        _SESSION_MAKERS[key] = sessionmaker(
            bind=get_engine(settings), autoflush=False, autocommit=False, expire_on_commit=False
        )
    return _SESSION_MAKERS[key]


def get_db() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
