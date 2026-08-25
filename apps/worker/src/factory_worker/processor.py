"""Claiming and executing one job.

Transaction boundaries are the whole story here, and there are three of them per job:

1. **Claim** commits immediately. A claim that stayed open for the job's duration would
   hold a row lock for minutes and make a crashed worker's job invisible until its
   connection timed out. Committing the claim with a lease means a dead worker's job is
   reclaimable the moment the lease lapses.
2. **Execute** runs the handler with its own session, so events it records commit
   together with the completion.
3. **Publish** happens *after* that commit — never inside it, because a rollback would
   otherwise announce events no replay will ever return.

Failures are recorded, not raised. The claim loop must survive a handler that throws;
that is what retry, backoff and the dead-letter state are for.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from factory_core.domain.ids import JobId
from factory_core.events import EventPublisher, EventStore
from factory_core.infrastructure.queue import Job, JobQueue, JobStatus
from factory_core.infrastructure.redis import EventBus
from factory_core.observability import bind_context, get_logger
from factory_core.persistence import SessionFactory, unit_of_work
from factory_worker.handlers import (
    HandlerRegistry,
    JobContext,
    UnknownJobTypeError,
)

logger = get_logger(__name__)

#: How long a claim is held before another worker may reclaim it.
LEASE_SECONDS = 60.0

#: Renew at a third of the lease, so two consecutive renewal failures still leave time.
RENEW_INTERVAL_SECONDS = LEASE_SECONDS / 3


@dataclass(slots=True)
class ProcessResult:
    """What happened to one claimed job."""

    job_id: JobId
    status: JobStatus
    error: str | None = None


class JobProcessor:
    """Claims one job at a time and runs its handler."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        registry: HandlerRegistry,
        event_bus: EventBus,
        worker_id: str,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry
        self._event_bus = event_bus
        self._worker_id = worker_id

    async def claim_one(self) -> Job | None:
        """Claim the next due job, committing the claim immediately."""
        async with unit_of_work(self._session_factory) as session:
            return await JobQueue(session).claim(
                worker_id=self._worker_id, lease_seconds=LEASE_SECONDS
            )

    async def process(self, job: Job) -> ProcessResult:
        """Run a job's handler and record the outcome.

        Never raises for a handler failure — the outcome is recorded on the job so it can
        be retried or dead-lettered.
        """
        with bind_context(
            project_id=str(job.project_id) if job.project_id else None,
        ):
            return await self._process(job)

    async def _process(self, job: Job) -> ProcessResult:
        handler = self._registry.get(job.type)
        if handler is None:
            # A job type this revision does not know. Fail it rather than crash: a
            # newer revision may have enqueued work an older worker cannot run.
            return await self._fail(job, UnknownJobTypeError(job.type))

        renewer = asyncio.create_task(self._renew_lease(JobId(job.id)))
        try:
            async with unit_of_work(self._session_factory) as session:
                publisher = EventPublisher(EventStore(session), self._event_bus)
                context = JobContext(publisher=publisher, worker_id=self._worker_id)
                await handler(job, context)
                await JobQueue(session).complete(JobId(job.id))
        except Exception as exc:
            # Deliberately broad: a handler is arbitrary code and any exception it raises
            # is a job failure, not a worker failure. The type is recorded; the message
            # is truncated by the queue and never logged, since it can echo user input.
            return await self._fail(job, exc)
        finally:
            renewer.cancel()

        # Only after the transaction has committed. See the module docstring.
        await publisher.publish_pending()
        logger.info("job.completed", job_id=str(job.id), job_type=job.type)
        return ProcessResult(job_id=JobId(job.id), status=JobStatus.COMPLETED)

    async def _fail(self, job: Job, error: Exception) -> ProcessResult:
        """Record a failure, letting the queue decide retry versus dead-letter."""
        detail = f"{type(error).__name__}: {error}"
        async with unit_of_work(self._session_factory) as session:
            status = await JobQueue(session).fail(JobId(job.id), error=detail)

        logger.warning(
            "job.failed",
            job_id=str(job.id),
            job_type=job.type,
            attempts=job.attempts,
            outcome=status.value,
            error=type(error).__name__,
        )
        return ProcessResult(job_id=JobId(job.id), status=status, error=detail)

    async def _renew_lease(self, job_id: JobId) -> None:
        """Keep the lease alive while a handler runs.

        Without this, a job legitimately taking longer than the lease would be reclaimed
        and run twice concurrently. Stops renewing when ownership is lost, which is the
        signal that another worker has already taken over.
        """
        while True:
            await asyncio.sleep(RENEW_INTERVAL_SECONDS)
            async with unit_of_work(self._session_factory) as session:
                held = await JobQueue(session).renew_lease(
                    job_id, worker_id=self._worker_id, lease_seconds=LEASE_SECONDS
                )
            if not held:
                logger.warning("job.lease_lost", job_id=str(job_id))
                return
