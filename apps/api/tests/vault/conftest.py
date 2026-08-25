"""Fixtures for the vault and configuration API tests.

These run against the **real database**, unlike the rest of ``apps/api/tests``: the vault's
providers use real repositories and a real key ring, so faking them would test the fakes
rather than the wiring. Only the session provider is overridden, and only to point at the
throwaway test database.

Scoped to this directory so the ``client`` fixture here does not collide with the
fake-backed one in ``apps/api/tests/conftest.py``.
"""

from __future__ import annotations

import base64
import os
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from factory_api.dependencies import get_session
from factory_api.main import create_app
from factory_core.config import (
    ApiSettings,
    DatabaseSettings,
    Environment,
    ObservabilitySettings,
    SecuritySettings,
    Settings,
)
from factory_core.config.email import EmailSettings, VerificationSettings
from factory_core.config.secrets import SecretsSettings
from factory_core.persistence import Base, create_engine, create_session_factory

pytestmark = pytest.mark.integration

SECRET_VALUE = "sk-plaintext-that-must-never-be-returned-8817"

#: Field names that could plausibly carry a plaintext credential in a *response*.
VALUE_FIELD_NAMES = frozenset({"value", "secret", "plaintext", "secret_value", "credential"})


def _database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    return url


def _settings(url: str) -> Settings:
    material = base64.b64encode(bytes(range(32))).decode("ascii")
    return Settings(
        environment=Environment.TEST,
        database=DatabaseSettings(url=url),  # type: ignore[arg-type]
        security=SecuritySettings(
            jwt_secret_key="test-secret-key-that-is-at-least-32-characters",  # type: ignore[arg-type]
            argon2_time_cost=1,
            argon2_memory_cost_kib=8192,
            argon2_parallelism=1,
        ),
        observability=ObservabilitySettings(service_name="factory-api-test", log_level="WARNING"),
        api=ApiSettings(docs_enabled=True),
        # Transport is pinned explicitly, not merely detached from the .env file: the
        # root conftest also loads .env into os.environ, and environment variables beat
        # `_env_file=None`. A developer with real SMTP configured would otherwise make
        # this suite send actual email and leave the console-only debug endpoint empty.
        email=EmailSettings(_env_file=None, transport="console"),  # type: ignore[call-arg]
        verification=VerificationSettings(_env_file=None, resend_cooldown_seconds=0),  # type: ignore[call-arg]
        secrets=SecretsSettings(_env_file=None, master_key=f"v1:{material}"),  # type: ignore[arg-type]
    )


# Set once the schema exists for this session. A session-scoped async fixture would need
# a session-scoped event loop, and SQLAlchemy engines are bound to the loop that created
# them; a module-level flag keeps the engine function-scoped and loop-safe. Same pattern
# as packages/core/tests/integration/conftest.py, for the same reason.
_schema_ready = False


@pytest.fixture
async def vault_app() -> AsyncIterator[FastAPI]:
    """The real application over a clean schema.

    Only the session provider is overridden — and only to point at the test database, not
    to fake it. Everything else is the production wiring.

    The schema is created once and truncated per test. Dropping and recreating twelve
    tables against a remote database on every test turned this file into a three-minute
    suite on its own.
    """
    url = _database_url()
    settings = _settings(url)
    application = create_app(settings)

    global _schema_ready
    engine = create_engine(settings.database, application_name="secrets-api-tests")
    async with engine.begin() as connection:
        if not _schema_ready:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
            _schema_ready = True
        else:
            tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
            await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    factory = create_session_factory(engine)

    async def real_session() -> AsyncIterator[object]:
        async with factory() as session:
            yield session
            await session.commit()

    application.dependency_overrides[get_session] = real_session
    yield application
    await engine.dispose()


@pytest.fixture
async def client(vault_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=vault_app)
    async with (
        vault_app.router.lifespan_context(vault_app),
        AsyncClient(transport=transport, base_url="http://test") as http,
    ):
        yield http


async def signed_in(client: AsyncClient) -> tuple[dict[str, str], str]:
    """Register, verify and create a project. Returns auth headers and the project id."""
    email = "vault-owner@example.com"
    password = "a-sufficiently-long-passphrase"
    await client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": "Vault Owner"},
    )
    code = (await client.get("/debug/verification-code", params={"email": email})).json()["code"]
    session = (await client.post("/auth/verify-email", json={"email": email, "code": code})).json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    project = await client.post("/projects", json={"name": "Vault Project"}, headers=headers)
    return headers, project.json()["id"]


__all__ = ["SECRET_VALUE", "VALUE_FIELD_NAMES", "client", "signed_in", "vault_app"]
