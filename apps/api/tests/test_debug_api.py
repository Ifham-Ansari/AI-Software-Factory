"""The debug verification-code endpoint.

Reachable only in development/test — see `factory_api.routers.debug`. These tests prove
the environment gate actually removes the route (not just that the handler behaves), and
that even where it exists it only ever serves the console transport.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from factory_api.dependencies import get_email_sender, get_user_repository
from factory_api.main import create_app
from factory_core.config import (
    ApiSettings,
    DatabaseSettings,
    Environment,
    ObservabilitySettings,
    SecuritySettings,
    Settings,
)
from factory_core.config.email import EmailSettings
from factory_core.domain.entities import User, UserStatus
from factory_core.domain.ids import new_user_id
from factory_core.infrastructure.email import ConsoleEmailSender, verification_email
from factory_core.testing import FakeUserRepository, RecordingEmailSender

pytestmark = pytest.mark.integration

EMAIL = "ada@example.com"


def _settings(environment: Environment, **overrides: object) -> Settings:
    fields: dict[str, object] = {
        "environment": environment,
        "database": DatabaseSettings(  # type: ignore[arg-type]
            url="postgresql://test:test@192.0.2.1:5432/test?connect_timeout=1"
        ),
        "security": SecuritySettings(
            jwt_secret_key="test-secret-key-that-is-at-least-32-characters",  # type: ignore[arg-type]
            argon2_time_cost=1,
            argon2_memory_cost_kib=8192,
            argon2_parallelism=1,
        ),
        "observability": ObservabilitySettings(
            service_name="factory-api-test", log_level="WARNING", log_format="json"
        ),
        "api": ApiSettings(docs_enabled=False),
    }
    fields.update(overrides)
    return Settings(**fields)  # type: ignore[arg-type]


def _has_debug_route(app: FastAPI) -> bool:
    # `app.routes` no longer flattens included routers in this FastAPI version, so the
    # OpenAPI schema — built from the same route tree — is the reliable way to ask
    # "is this path actually routable".
    return "/debug/verification-code" in app.openapi()["paths"]


class TestRouterGating:
    """Whether the route exists at all — the real security boundary here."""

    def test_absent_in_staging(self) -> None:
        assert not _has_debug_route(create_app(_settings(Environment.STAGING)))

    def test_absent_in_production(self) -> None:
        settings = _settings(
            Environment.PRODUCTION,
            email=EmailSettings(
                transport="smtp",
                smtp_host="smtp.example.com",
                from_address="no-reply@example.com",
            ),
        )
        assert not _has_debug_route(create_app(settings))

    def test_present_in_development(self) -> None:
        assert _has_debug_route(create_app(_settings(Environment.DEVELOPMENT)))

    def test_present_in_test(self) -> None:
        assert _has_debug_route(create_app(_settings(Environment.TEST)))


class TestDebugEndpointBehavior:
    """Behaviour where the route does exist."""

    def _make_user(self) -> User:
        now = datetime.now(UTC)
        return User(
            id=new_user_id(),
            email=EMAIL,
            display_name="Ada Lovelace",
            status=UserStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )

    async def test_returns_the_last_code_for_a_known_address(self) -> None:
        app = create_app(_settings(Environment.TEST))
        users = FakeUserRepository()
        user = self._make_user()
        users.users[user.id] = user

        sender = ConsoleEmailSender()
        await sender.send(
            verification_email(
                to=EMAIL, display_name="Ada", code="123456", expires_in_minutes=10
            )
        )

        app.dependency_overrides[get_user_repository] = lambda: users
        app.dependency_overrides[get_email_sender] = lambda: sender

        transport = ASGITransport(app=app)
        async with (
            app.router.lifespan_context(app),
            AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            response = await client.get(
                "/debug/verification-code", params={"email": EMAIL}
            )

        assert response.status_code == 200, response.text
        assert response.json()["code"] == "123456"

    async def test_404_for_an_unknown_address(self) -> None:
        app = create_app(_settings(Environment.TEST))
        app.dependency_overrides[get_user_repository] = lambda: FakeUserRepository()
        app.dependency_overrides[get_email_sender] = lambda: ConsoleEmailSender()

        transport = ASGITransport(app=app)
        async with (
            app.router.lifespan_context(app),
            AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            response = await client.get(
                "/debug/verification-code", params={"email": "nobody@example.com"}
            )

        assert response.status_code == 404

    async def test_404_when_the_transport_is_not_console(self) -> None:
        """Selecting SMTP in test/dev must not resurrect a way to read a code."""
        app = create_app(_settings(Environment.TEST))
        users = FakeUserRepository()
        user = self._make_user()
        users.users[user.id] = user

        app.dependency_overrides[get_user_repository] = lambda: users
        app.dependency_overrides[get_email_sender] = lambda: RecordingEmailSender()

        transport = ASGITransport(app=app)
        async with (
            app.router.lifespan_context(app),
            AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            response = await client.get(
                "/debug/verification-code", params={"email": EMAIL}
            )

        assert response.status_code == 404
