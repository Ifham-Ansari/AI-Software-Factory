"""Application startup and shutdown.

Startup order is deliberate: logging first (so a configuration failure is logged in the
same structured format as everything else), then secret registration with the redactor,
then state construction.

Registering configuration secrets with the redactor *before* any request is served is
what makes the "no secret in any log line" guarantee hold for values that arrive from the
environment rather than from a user.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from factory_api.state import build_state
from factory_core.config import Settings
from factory_core.observability import configure_logging, get_logger, get_redactor
from factory_core.persistence import dispose_engine

logger = get_logger(__name__)

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def _register_secrets(settings: Settings) -> None:
    """Teach the redactor every secret this process holds.

    Registered as whole values *and* as the password component of the database URL: a
    driver error commonly echoes just the password, not the entire connection string.
    """
    redactor = get_redactor()
    database_url = settings.database.url.get_secret_value()
    redactor.register(
        database_url,
        settings.security.jwt_secret_key.get_secret_value(),
    )
    password = _url_password(database_url)
    if password:
        redactor.register(password)


def _url_password(url: str) -> str | None:
    """Extract the password from a connection URL, if it has one."""
    _, separator, remainder = url.partition("://")
    if not separator or "@" not in remainder:
        return None
    credentials = remainder.split("@", 1)[0]
    if ":" not in credentials:
        return None
    return credentials.split(":", 1)[1] or None


def build_lifespan(settings: Settings) -> Lifespan:
    """Build the lifespan context manager for an application.

    Takes settings rather than reading them itself so tests can start the app against a
    throwaway configuration without touching process-wide state.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(
            level=settings.observability.log_level,
            log_format=settings.observability.log_format,
            service_name=settings.observability.service_name,
        )
        _register_secrets(settings)

        state = build_state(settings)
        app.state.app_state = state
        logger.info(
            "api.started",
            environment=settings.environment.value,
            docs_enabled=settings.api.docs_enabled,
        )
        try:
            yield
        finally:
            # Close pooled connections so the database is not left holding sockets for a
            # process that has exited.
            await dispose_engine(state.engine)
            logger.info("api.stopped")

    return lifespan
