"""Integration fixtures: a real PostgreSQL database.

These tests need a real database and are skipped without one. They are not optional — they
cover what fakes structurally cannot:

* that the generated SQL actually scopes by owner (the central security property),
* that constraints, cascades and check constraints behave as declared,
* that transactions roll back,
* that migrations apply and revert.

Set ``TEST_DATABASE_URL`` to run them, in the environment or in ``.env``. CI always sets
it; see ``.github/workflows/ci.yml``.

⚠️ **The target database is wiped.** Point it at a throwaway — a dedicated Neon branch or
database, or a local container. Never at the database in ``DATABASE_URL``.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from factory_core.config import DatabaseSettings
from factory_core.persistence import Base, create_engine, create_session_factory

SKIP_REASON = (
    "TEST_DATABASE_URL is not set. Integration tests need a real PostgreSQL database; "
    "they verify SQL-level behaviour (owner scoping, constraints, transactions) that "
    "in-memory fakes cannot."
)

pytestmark = pytest.mark.integration


def _database_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def database_url() -> str:
    """The throwaway database to test against."""
    url = _database_url()
    if url is None:
        pytest.skip(SKIP_REASON)
    return url


# Set once the schema has been built for this session. A session-scoped async fixture
# would need a session-scoped event loop, and SQLAlchemy engines are bound to the loop
# that created them — mixing the two produces intermittent "attached to a different loop"
# failures. A module-level flag keeps the engine function-scoped and loop-safe.
_schema_ready = False


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    """An engine over an empty schema.

    The schema is created once per session, then truncated before each test. Dropping and
    recreating every table per test costs a round trip per table per test, which against a
    remote database turned a 30-second suite into a six-minute one.

    It is built from ``Base.metadata`` rather than by running migrations. Those are
    verified separately in ``test_migrations.py``; building directly here keeps a migration
    bug from failing every unrelated test with a confusing error.
    """
    global _schema_ready

    settings = DatabaseSettings(url=database_url)  # type: ignore[arg-type]
    test_engine = create_engine(settings, application_name="factory-tests")

    async with test_engine.begin() as connection:
        if not _schema_ready:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
            _schema_ready = True
        else:
            # RESTART IDENTITY also resets sequences; CASCADE follows foreign keys, so
            # truncation order does not matter.
            tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
            await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))

    yield test_engine

    await test_engine.dispose()


@pytest.fixture
def rebuild_schema_after() -> Iterator[None]:
    """Force the shared schema to be rebuilt after this test.

    The migration tests create and destroy the schema themselves, which leaves the cached
    flag lying about what exists. Requesting this fixture makes them safe to run in any
    position without breaking the tests around them.

    Exposed as a fixture rather than an importable function because the test roots are not
    packages — see the ``--import-mode=importlib`` note in pyproject.toml.
    """
    global _schema_ready
    yield
    _schema_ready = False


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session over the empty schema, rolled back at the end.

    The rollback covers anything the test left uncommitted; the truncation in ``engine``
    covers anything it committed.
    """
    factory = create_session_factory(engine)
    async with factory() as db_session:
        yield db_session
        await db_session.rollback()
