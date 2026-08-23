"""Worker entrypoint: ``uv run dev-worker``."""

from __future__ import annotations

import asyncio
import sys

from factory_core.config import load_settings
from factory_core.errors import ConfigurationError
from factory_core.observability import configure_logging, get_logger, get_redactor
from factory_core.runtime import configure_event_loop, event_loop_factory

logger = get_logger(__name__)


async def _run() -> None:
    from factory_worker.runner import Worker, install_signal_handlers

    settings = load_settings()
    configure_logging(
        level=settings.observability.log_level,
        log_format=settings.observability.log_format,
        service_name="factory-worker",
    )
    # Same guarantee as the API, from the same source: every configured secret is known
    # to the redactor before anything can log it.
    get_redactor().register(*settings.secret_values())

    worker = Worker(settings)
    install_signal_handlers(worker, asyncio.get_running_loop())
    await worker.run()


def main() -> int:
    """Run the worker until stopped.

    Returns:
        Process exit code. ``1`` when configuration is invalid.
    """
    # psycopg cannot use Windows' default ProactorEventLoop. The policy covers any
    # loop created indirectly; the explicit factory covers the one created here.
    configure_event_loop()
    try:
        asyncio.run(_run(), loop_factory=event_loop_factory())
    except ConfigurationError as exc:
        # Logging is not configured yet when this fires, and the message names every
        # offending environment variable.
        print(f"\n{exc.message}\n", file=sys.stderr)  # noqa: T201
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
