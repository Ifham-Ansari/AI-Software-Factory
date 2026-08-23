"""Process-wide application state.

Everything expensive to build — the connection pool, the password hasher with its
precomputed dummy hash, the token issuer — is constructed once at startup and held here.
Dependencies read it from ``request.app.state``.

Holding it in one typed object rather than as loose attributes on ``app.state`` means the
type checker catches a missing or misspelled dependency instead of a request failing at
runtime with ``AttributeError``.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from factory_core.application.health import DependencyProbe, HealthService
from factory_core.config import Settings
from factory_core.persistence import SessionFactory, create_engine, create_session_factory
from factory_core.security import AccessTokenIssuer, PasswordHasher


@dataclass(slots=True)
class AppState:
    """Long-lived objects shared across requests."""

    settings: Settings
    engine: AsyncEngine
    session_factory: SessionFactory
    hasher: PasswordHasher
    issuer: AccessTokenIssuer
    health: HealthService


def build_state(settings: Settings) -> AppState:
    """Construct application state from settings.

    Pure: it opens no connections and performs no I/O, so it is safe to call in a test
    without a database. The pool connects lazily on first use.
    """
    engine = create_engine(settings.database, application_name="factory-api")
    session_factory = create_session_factory(engine)

    health = HealthService(timeout_seconds=settings.api.health_timeout_seconds)
    health.register("database", _database_probe(session_factory))

    return AppState(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        hasher=PasswordHasher(
            time_cost=settings.security.argon2_time_cost,
            memory_cost_kib=settings.security.argon2_memory_cost_kib,
            parallelism=settings.security.argon2_parallelism,
        ),
        issuer=AccessTokenIssuer(
            secret_key=settings.security.jwt_secret_key.get_secret_value(),
            algorithm=settings.security.jwt_algorithm,
            issuer=settings.security.jwt_issuer,
            audience=settings.security.jwt_audience,
            ttl_seconds=settings.security.access_token_ttl_seconds,
        ),
        health=health,
    )


def _database_probe(session_factory: SessionFactory) -> DependencyProbe:
    """Build a probe that verifies the database answers.

    ``SELECT 1`` rather than a table query on purpose: readiness should report that the
    connection works, not couple itself to the schema. A missing table is a deployment
    problem for migrations to catch, not something to flap the readiness probe.
    """

    async def probe() -> None:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))

    return probe
