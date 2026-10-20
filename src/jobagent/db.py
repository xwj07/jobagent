"""Engine/session plumbing. Kept separate from models to avoid circular imports."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def create_engine_from_url(url: str) -> Engine:
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        # FastAPI/threads and CLI share the connection; SQLite needs this flag.
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        # SQLite ignores foreign keys by default; enable them per connection.
        @event.listens_for(engine, "connect")
        def _enable_fk(dbapi_conn, _record):  # pragma: no cover - trivial hook
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def create_session_factory(url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=create_engine_from_url(url), expire_on_commit=False)


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _ensure() -> sessionmaker[Session]:
    global _engine, _session_factory
    if _session_factory is None:
        _engine = create_engine_from_url(settings.database_url)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _session_factory


def get_session_factory() -> sessionmaker[Session]:
    return _ensure()


def init_db(url: str | None = None) -> None:
    """Create tables. Safe to call repeatedly (create_all is idempotent)."""
    from . import models  # noqa: F401  (import registers ORM classes on Base.metadata)

    engine = create_engine_from_url(url) if url else _ensure().kw["bind"]
    Base.metadata.create_all(engine)
