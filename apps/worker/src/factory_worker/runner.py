"""Worker run loop.

Claims jobs one at a time, runs them, and drains cleanly on SIGTERM.

**Graceful drain** is the part worth reading carefully. On shutdown the worker stops
*claiming* but finishes the job it is holding. Abandoning it would not lose the work — the
lease would lapse and another worker would reclaim it — but it would mean every deploy
re-runs whatever was in flight, and at-least-once delivery is a guarantee to be spent
sparingly rather than routinely.

Polling rather than ``LISTEN/NOTIFY``: a poll is simpler, survives a dropped connection
with no reconnect logic, and at our volumes the added latency is bounded by the idle
interval. Revisit if sub-second job start-up ever matters.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import uuid

from sqlalchemy import text

from factory_core.config import Settings
from factory_core.infrastructure.queue import Job
from factory_core.infrastructure.redis import EventBus, RedisGateway, create_redis
from factory_core.observability import get_logger
from factory_core.persistence import (
    SessionFactory,
    create_engine,
    create_session_factory,
    dispose_engine,
)
from factory_worker.handlers import build_registry
from factory_worker.processor import JobProcessor

logger = get_logger(__name__)

#: How long to wait before polling again when the queue was empty.
IDLE_POLL_SECONDS = 1.0

#: How long a drain may take before the worker exits anyway. Bounded so a wedged handler
#: cannot block a deployment indefinitely; the lease then expires and the job is reclaimed.
DRAIN_TIMEOUT_SECONDS = 30.0


def build_worker_id() -> str:
    """Identify this worker instance.

    Host plus PID plus a random suffix: the first two make a log line traceable to a
    process, and the suffix keeps ids unique when two workers share a container name.
    """
    host = os.getenv("HOSTNAME") or "local"
    return f"{host}-{os.getpid()}-{uuid.uuid4().hex[:6]}"


class Worker:
    """The workflow executor process."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._stopping = asyncio.Event()
        self._worker_id = build_worker_id()
        self._draining = False

    @property
    def worker_id(self) -> str:
        """This instance's identifier, as recorded on claimed jobs."""
        return self._worker_id

    def request_stop(self) -> None:
        """Ask the worker to finish its current job and exit."""
        if not self._stopping.is_set():
            logger.info("worker.stop_requested", worker_id=self._worker_id)
            self._stopping.set()

    async def run(self) -> None:
        """Start the worker and block until stopped."""
        engine = create_engine(self._settings.database, application_name="factory-worker")
        session_factory = create_session_factory(engine)
        gateway = RedisGateway(create_redis(self._settings.redis))
        registry = build_registry()

        processor = JobProcessor(
            session_factory=session_factory,
            registry=registry,
            event_bus=EventBus(gateway),
            worker_id=self._worker_id,
        )

        try:
            await self._verify_database(session_factory)
            logger.info(
                "worker.started",
                worker_id=self._worker_id,
                environment=self._settings.environment.value,
                handlers=sorted(registry.known_types),
                redis=gateway.is_available,
            )
            await self._loop(processor)
        finally:
            await gateway.close()
            await dispose_engine(engine)
            logger.info("worker.stopped", worker_id=self._worker_id)

    async def _loop(self, processor: JobProcessor) -> None:
        """Claim and run jobs until asked to stop.

        Two different shutdown behaviours, and the difference is deliberate:

        * A **claim** in flight is abandoned. It has claimed nothing yet, so cancelling it
          rolls its transaction back and costs nothing. Waiting for it would make
          shutdown as slow as the database's connect timeout — minutes, if the database
          is unreachable at exactly the wrong moment.
        * A **job** in flight is shielded and runs to completion. Abandoning it would not
          lose the work (the lease lapses and another worker reclaims it), but it would
          mean every deploy re-runs whatever was in flight, and at-least-once delivery is
          a guarantee to spend sparingly.
        """
        while not self._stopping.is_set():
            job = await self._claim_or_stop(processor)
            if job is None:
                continue

            self._draining = True
            try:
                await asyncio.shield(processor.process(job))
            finally:
                self._draining = False

    async def _claim_or_stop(self, processor: JobProcessor) -> Job | None:
        """Claim the next job, giving up immediately if a stop arrives first.

        Returns ``None`` when there was nothing to claim, the claim failed, or the worker
        is stopping — the caller re-checks the stop flag either way.
        """
        claim = asyncio.create_task(processor.claim_one())
        stop = asyncio.create_task(self._stopping.wait())
        try:
            done, _ = await asyncio.wait({claim, stop}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stop.cancel()

        if claim not in done:
            # Stop won the race. Cancel the claim so its transaction rolls back rather
            # than committing a claim nobody will process.
            claim.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await claim
            return None

        try:
            job = claim.result()
        except Exception as exc:
            # A database blip must not kill the worker. Back off one tick and retry;
            # the alternative is a crash loop that a restart policy papers over.
            logger.warning("worker.claim_failed", error=type(exc).__name__)
            await self._sleep_or_stop(IDLE_POLL_SECONDS)
            return None

        if job is None:
            await self._sleep_or_stop(IDLE_POLL_SECONDS)
        return job

    async def _sleep_or_stop(self, seconds: float) -> None:
        """Wait, waking early if a stop is requested.

        Waiting on the stop event rather than sleeping blindly is what makes SIGTERM feel
        immediate on an idle worker instead of taking up to a full poll interval.
        """
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stopping.wait(), timeout=seconds)

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
