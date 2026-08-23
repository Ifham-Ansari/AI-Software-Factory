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

    Sourced from ``Settings.secret_values()`` so that adding a credential to configuration
    protects it automatically. A secret that is configured but never registered here is a
    secret that can reach a log line.

    The redactor also derives the password component of any credentialed URL it is
    given, so a driver error echoing just the password is caught too.
    """
    get_redactor().register(*settings.secret_values())


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
            # Booleans only — which optional services are configured, never their values.
            integrations=settings.configured_integrations(),
        )
        try:
            yield
        finally:
            # Close pooled connections so the database is not left holding sockets for a
            # process that has exited.
            await dispose_engine(state.engine)
            logger.info("api.stopped")

    return lifespan
