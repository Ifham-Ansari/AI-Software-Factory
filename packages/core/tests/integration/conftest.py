"""Integration fixtures: a real PostgreSQL database.

These tests need a real database and are skipped without one. They are not optional — they
cover what fakes structurally cannot:

* that the generated SQL actually scopes by owner (the central security property),
* that constraints, cascades and check constraints behave as declared,
* that transactions roll back,
* that migrations apply and revert.

Set ``TEST_DATABASE_URL`` to run them. CI always sets it; see ``.github/workflows/ci.yml``.
The target database is wiped, so it must be a throwaway.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from factory_core.config import DatabaseSettings
from factory_core.persistence import (
    Base,
    create_engine,
    create_session_factory,
)

SKIP_REASON = (
    "TEST_DATABASE_URL is not set. Integration tests need a real PostgreSQL database; "
    "they verify SQL-level behaviour (owner scoping, constraints, transactions) that "
    "in-memory fakes cannot."
)

pytestmark = pytest.mark.integration


def _database_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL")


requires_database = pytest.mark.skipif(_database_url() is None, reason=SKIP_REASON)


@pytest.fixture(scope="session")
def database_url() -> str:
    """The throwaway database to test against."""
    url = _database_url()
    if url is None:
        pytest.skip(SKIP_REASON)
    return url


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    """An engine bound to the test database, with a freshly created schema.

    The schema is built from ``Base.metadata`` rather than by running migrations. Those
    are verified separately in ``test_migrations.py``; building directly here keeps a
    migration bug from failing every unrelated test with a confusing error.
    """
    settings = DatabaseSettings(url=database_url)  # type: ignore[arg-type]
    test_engine = create_engine(settings, application_name="factory-tests")

    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    yield test_engine

    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session in a transaction that is always rolled back.

    Every test starts from the same empty schema and leaves nothing behind, so tests can
    run in any order without interfering.
    """
    factory = create_session_factory(engine)
    async with factory() as db_session:
        yield db_session
        await db_session.rollback()
