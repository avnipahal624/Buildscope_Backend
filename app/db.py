"""Database engine/session handling.

The engine is created lazily so tests can call configure("sqlite://") first.
"""
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_engine = None
_SessionLocal = None


def configure(url: str | None = None, **engine_kwargs):
    global _engine, _SessionLocal
    url = url or get_settings().database_url
    _engine = create_engine(url, pool_pre_ping=True, **engine_kwargs)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_engine():
    if _engine is None:
        configure()
    return _engine


def get_session_factory():
    if _SessionLocal is None:
        configure()
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def init_db():
    """Create all tables (use Alembic migrations once the schema stabilises)."""
    from app import models  # noqa: F401  (registers tables)

    models.Base.metadata.create_all(get_engine())
