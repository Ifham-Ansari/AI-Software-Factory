"""Development entrypoint: ``uv run dev-api``.

Runs the uvicorn server directly rather than through ``uvicorn.run()`` so this process
owns the event loop. uvicorn picks its own loop via an internal factory that hard-codes
``ProactorEventLoop`` on Windows, which psycopg cannot use — and it ignores the asyncio
policy, so setting that is not enough. Owning the loop here is what makes the API able to
reach the database on a Windows developer machine.

On Linux, where CI and production run, uvicorn already selects a selector loop and
``event_loop_factory()`` returns ``None``, so this is the ordinary path with no special
casing.
"""

from __future__ import annotations

import asyncio
import sys

import uvicorn

from factory_core.config import Settings, load_settings
from factory_core.errors import ConfigurationError
from factory_core.runtime import event_loop_factory


def _build_server(settings: Settings) -> uvicorn.Server:
    """Configure the server from application settings.

    Reload is off in deployed environments: it doubles memory and watches the filesystem
    for changes that will never happen there.
    """
    config = uvicorn.Config(
        "factory_api.main:create_app",
        factory=True,
        host=settings.api.host,
        port=settings.api.port,
        reload=not settings.environment.is_deployed,
        log_config=None,  # structlog owns logging; see observability/logging.py
    )
    return uvicorn.Server(config)


def main() -> int:
    """Run the API until interrupted.

    Returns:
        Process exit code. ``1`` when configuration is invalid.
    """
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        # Printed rather than logged: logging is not configured yet, and this message is
        # the entire point of the failure. It names every offending variable.
        print(f"\n{exc.message}\n", file=sys.stderr)  # noqa: T201
        return 1

    server = _build_server(settings)

    if server.config.reload:
        # The reloader supervises worker subprocesses and needs uvicorn's own runner.
        # Those subprocesses get a selector loop from uvicorn regardless of platform,
        # because it treats the subprocess case differently.
        server.run()
        return 0

    try:
        asyncio.run(server.serve(), loop_factory=event_loop_factory())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
