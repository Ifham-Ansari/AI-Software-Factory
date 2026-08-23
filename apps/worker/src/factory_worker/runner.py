"""Worker run loop.

Phase 1 scope is deliberately narrow. The worker exists as a process now — it starts,
configures logging identically to the API, verifies it can reach the database, and shuts
down gracefully — but it has no work to do yet.

The durable job queue and the claim loop are Phase 2 (F-213, F-214), and the LangGraph
execution it will eventually drive is Phase 3. Building the process shell now means
Phase 1 can satisfy "one documented command starts API, worker, and web" without
pretending the queue exists.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

from sqlalchemy import text

from factory_core.config import Settings
from factory_core.observability import get_logger
from factory_core.persistence import (
    SessionFactory,
    create_engine,
    create_session_factory,
    dispose_engine,
)

logger = get_logger(__name__)

# How often the idle loop wakes to check for shutdown. Short enough that SIGTERM feels
# immediate, long enough that an idle worker is not a busy loop.
_TICK_SECONDS = 1.0


class Worker:
    """The workflow executor process."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._stopping = asyncio.Event()

    def request_stop(self) -> None:
        """Ask the worker to finish its current tick and exit."""
        if not self._stopping.is_set():
            logger.info("worker.stop_requested")
            self._stopping.set()

    async def run(self) -> None:
        """Start the worker and block until stopped."""
        engine = create_engine(self._settings.database, application_name="factory-worker")
        session_factory = create_session_factory(engine)

        try:
            await self._verify_database(session_factory)
            logger.info("worker.started", environment=self._settings.environment.value)
            await self._loop()
        finally:
            await dispose_engine(engine)
            logger.info("worker.stopped")

    async def _loop(self) -> None:
        """Idle until asked to stop.

        Phase 2 replaces the sleep with a queue claim. The shape stays: wake, do at most
        one unit of work, check for shutdown, repeat.
        """
        while not self._stopping.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=_TICK_SECONDS)

    @staticmethod
    async def _verify_database(session_factory: SessionFactory) -> None:
        """Fail fast if the database is unreachable at startup.

        A worker that starts without a database would sit in its loop looking healthy
        while being unable to do anything, which is worse than not starting at all.
        """
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        logger.info("worker.database_ready")


def install_signal_handlers(worker: Worker, loop: asyncio.AbstractEventLoop) -> None:
    """Route termination signals to a graceful stop.

    ``add_signal_handler`` is not implemented on Windows, so this falls back to
    ``signal.signal``. Without the fallback a developer's Ctrl+C would raise inside the
    loop instead of draining cleanly.
    """
    for name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, worker.request_stop)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, lambda _s, _f: worker.request_stop())
