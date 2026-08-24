"""Application factory.

``create_app`` accepts settings so a test can build an application against a throwaway
configuration without mutating process-wide state. Production calls it with no argument
and gets the environment-derived settings.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from factory_api import __version__
from factory_api.errors import register_exception_handlers
from factory_api.lifespan import build_lifespan
from factory_api.middleware import REQUEST_ID_HEADER, CorrelationMiddleware
from factory_api.routers import auth, health, projects
from factory_api.routers.debug import build_debug_router
from factory_core.config import Settings, get_settings

DESCRIPTION = """
Control-plane API for the AI Software Factory.

Every error response uses a single envelope with a stable `error.code`; branch on that
rather than on status text. Every response carries an `X-Request-ID` header that
correlates it with server logs.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application."""
    resolved = settings or get_settings()

    app = FastAPI(
        title="AI Software Factory API",
        description=DESCRIPTION,
        version=__version__,
        lifespan=build_lifespan(resolved),
        # Documentation is disabled in production by configuration, and that is enforced
        # at settings level too: production refuses to start with it enabled.
        docs_url="/docs" if resolved.api.docs_enabled else None,
        redoc_url="/redoc" if resolved.api.docs_enabled else None,
        openapi_url="/openapi.json" if resolved.api.docs_enabled else None,
        root_path=resolved.api.root_path,
    )

    # Middleware is applied bottom-up, so CORS is added first and therefore runs
    # outermost. That matters: a rejected pre-flight should not allocate a request id.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.api.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
        max_age=600,
    )
    app.add_middleware(CorrelationMiddleware)

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(projects.router)

    # Never registered in a deployed environment: this is how e2e tests read a
    # verification code without email delivery, and it must not exist anywhere reachable
    # by a real user.
    if not resolved.environment.is_deployed:
        app.include_router(build_debug_router())

    return app
