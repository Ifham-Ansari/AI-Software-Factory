"""Async engine and connection pooling.

psycopg 3 is the only PostgreSQL driver in this system (architecture.md §15). Two
consequences show up here:

* Neon routes through a PgBouncer-compatible pooler. Server-side prepared statements do
  not survive transaction-mode pooling, so ``prepare_threshold=None`` disables them.
  Without this, a connection reused by the pooler raises "prepared statement already
  exists" under concurrency — intermittently, and only under load.
* ``pool_pre_ping`` costs one round trip per checkout and is worth it against a serverless
  database that suspends idle computes: without it the first request after a scale-to-zero
  fails with a stale connection instead of transparently reconnecting.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from factory_core.config import DatabaseSettings

CONNECT_ARGS: dict[str, object] = {
    "prepare_threshold": None,
}


def create_engine(settings: DatabaseSettings, *, application_name: str = "factory") -> AsyncEngine:
    """Build the async engine.

    Args:
        settings: Database configuration.
        application_name: Reported to PostgreSQL, so ``pg_stat_activity`` distinguishes
            API connections from worker connections during an incident.
    """
    return create_async_engine(
        settings.url.get_secret_value(),
        echo=settings.echo,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_timeout=settings.pool_timeout_seconds,
        pool_recycle=settings.pool_recycle_seconds,
        pool_pre_ping=True,
        connect_args={
            **CONNECT_ARGS,
            "application_name": application_name,
        },
    )


async def dispose_engine(engine: AsyncEngine) -> None:
    """Close every pooled connection.

    Called during graceful shutdown so the database does not hold connections open for a
    process that has already exited.
    """
    await engine.dispose()
