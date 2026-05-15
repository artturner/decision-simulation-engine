"""
Database engine and session factory.

Usage in FastAPI endpoints (dependency injection)::

    from app.db.session import get_db

    @router.get("/example")
    def example(db: Session = Depends(get_db)):
        ...

The ``get_db`` generator opens a session, yields it, and guarantees
cleanup via a ``finally`` block even if the endpoint raises an exception.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    # Pool settings appropriate for a single-process sync API.
    pool_pre_ping=True,   # detect stale connections before use
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
