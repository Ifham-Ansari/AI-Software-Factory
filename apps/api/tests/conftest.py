"""API test fixtures.

The application under test is the real one: real routing, real middleware, real token
verification, real services, real error rendering. Only the four repository providers are
replaced, which swaps the database for in-memory storage and nothing else.

That boundary is chosen deliberately. Overriding higher up (say, ``get_current_user``)
would stop testing the thing most likely to be wrong — the authentication chain. Overriding
lower down would need a database. What these tests cannot prove is that the *SQL* is
correct, and especially that owner scoping holds in the generated queries; that is what
``packages/core/tests/integration`` is for.
"""

from __future__ import annotations

import io
from collections.abc import AsyncIterator, Iterator
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from factory_api.dependencies import (
    get_audit_repository,
    get_current_user_id,
    get_email_sender,
    get_project_repository,
    get_refresh_token_repository,
    get_session,
    get_user_repository,
    get_verification_repository,
)
from factory_api.main import create_app
from factory_core.config import (
    ApiSettings,
    DatabaseSettings,
    Environment,
    ObservabilitySettings,
    SecuritySettings,
    Settings,
)
from factory_core.config.email import VerificationSettings
from factory_core.domain.ids import UserId
from factory_core.observability import configure_logging, get_redactor
from factory_core.testing import (
    FakeAuditRepository,
    FakeProjectRepository,
    FakeProjectStore,
    FakeRefreshTokenRepository,
    FakeUserRepository,
    FakeVerificationRepository,
    RecordingEmailSender,
)

from .helpers import ApiHelper


class Fakes:
    """Every in-memory repository backing one test application."""

    def __init__(self) -> None:
        self.users = FakeUserRepository()
        self.tokens = FakeRefreshTokenRepository()
        self.audit = FakeAuditRepository()
        self.projects = FakeProjectStore()
        self.verifications = FakeVerificationRepository()
        self.emails = RecordingEmailSender()


@pytest.fixture
def fakes() -> Fakes:
    """In-memory storage shared by one test application."""
    return Fakes()


@pytest.fixture
def settings() -> Settings:
    """Test configuration.

    Argon2 cost is dialled right down: production parameters are ~50 ms per hash, and a
    suite with dozens of registrations would spend nearly all its time hashing.
    """
    return Settings(
        environment=Environment.TEST,
        # TEST-NET-1 (RFC 5737) is guaranteed unroutable, with a short connect timeout.
        # Every repository is faked, so nothing should reach the database — but the
        # readiness probe deliberately does, and pointing it at localhost would make the
        # test's speed and result depend on whether the developer happens to be running
        # Postgres.
        database=DatabaseSettings(  # type: ignore[arg-type]
            url="postgresql://test:test@192.0.2.1:5432/test?connect_timeout=1"
        ),
        security=SecuritySettings(
            jwt_secret_key="test-secret-key-that-is-at-least-32-characters",  # type: ignore[arg-type]
            argon2_time_cost=1,
            argon2_memory_cost_kib=8192,
            argon2_parallelism=1,
        ),
        # WARNING keeps request logs out of test output; tests that assert on logging
        # reconfigure through the log_stream fixture.
        observability=ObservabilitySettings(service_name="factory-api-test", log_level="WARNING"),
        api=ApiSettings(docs_enabled=True),
        # The verification service has no controllable clock in the API layer (it uses
        # wall-clock time), so a non-zero cooldown would make resend tests race against
        # real seconds. Zeroing it here keeps them deterministic; the cooldown's own
        # enforcement is proven directly in the unit suite, which does control the clock.
        verification=VerificationSettings(resend_cooldown_seconds=0),
    )


@pytest.fixture
def log_stream(client: AsyncClient) -> Iterator[io.StringIO]:
    """Capture structured log output produced while handling requests.

    Depends on ``client`` so it runs *after* the lifespan has configured logging.
    Configuring first would just be overwritten, and the buffer would stay empty.
    """
    buffer = io.StringIO()
    configure_logging(level="DEBUG", log_format="json", service_name="test", stream=buffer)
    yield buffer
    get_redactor().clear()


@pytest.fixture
def app(settings: Settings, fakes: Fakes) -> FastAPI:
    """The real application, with only the database boundary replaced."""
    application = create_app(settings)

    async def no_session() -> AsyncIterator[None]:
        """Stand in for the request transaction.

        Every repository provider is overridden, so nothing should ever ask for a
        session. This exists so that an un-overridden dependency surfaces here instead of
        trying to open a connection to a database that is not running.
        """
        yield None

    def scoped_projects(
        actor_id: Annotated[UserId, Depends(get_current_user_id)],
    ) -> FakeProjectRepository:
        """Mirror the real provider: scope comes from the verified access token."""
        return FakeProjectRepository(fakes.projects, owner_id=actor_id)

    application.dependency_overrides[get_session] = no_session
    application.dependency_overrides[get_user_repository] = lambda: fakes.users
    application.dependency_overrides[get_refresh_token_repository] = lambda: fakes.tokens
    application.dependency_overrides[get_audit_repository] = lambda: fakes.audit
    application.dependency_overrides[get_verification_repository] = lambda: fakes.verifications
    application.dependency_overrides[get_email_sender] = lambda: fakes.emails
    application.dependency_overrides[get_project_repository] = scoped_projects
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """An HTTP client bound to the test application.

    ``ASGITransport`` calls the app in-process, so requests exercise the full middleware
    and routing stack without binding a socket. It does **not** run the lifespan, so that
    is driven explicitly — otherwise ``app.state.app_state`` is never built and every
    request fails with an opaque 500.

    Running the real lifespan is also better coverage: it exercises logging setup and
    secret registration exactly as production does.
    """
    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://test") as http,
    ):
        yield http


@pytest.fixture
def api(client: AsyncClient, fakes: Fakes) -> ApiHelper:
    """Request helpers bound to the test client."""
    return ApiHelper(client, fakes.emails)
