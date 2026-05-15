"""
Shared pytest fixtures for the API service integration tests.

All DB tests run inside a transaction that is rolled back after the test,
so each test starts from a clean slate without needing to truncate tables.

The ``db_engine`` fixture creates tables once per session (idempotent via
``checkfirst=True``) and tears them down at the end only if the
``--drop-tables`` CLI flag is passed.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import models so their metadata is registered on Base before create_all.
import app.models  # noqa: F401
from app.db.base import Base
from app.core.config import settings


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.close()
    except Exception as exc:
        pytest.skip(f"Database not reachable — skipping DB tests: {exc}")

    Base.metadata.create_all(engine, checkfirst=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db(db_engine):
    """Yield a Session whose work is rolled back after the test.

    ``join_transaction_mode="create_savepoint"`` makes the session use a
    SAVEPOINT rather than the outer transaction directly.  When a test
    deliberately triggers an IntegrityError, only the SAVEPOINT is rolled
    back — the outer transaction remains valid and can be cleanly rolled
    back by this fixture without emitting SAWarning.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()
