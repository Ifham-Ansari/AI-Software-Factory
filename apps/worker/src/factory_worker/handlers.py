"""Job handler registry.

A handler is an async function taking a :class:`Job` and a :class:`JobContext`. The
registry maps a job *type* to one, which keeps the claim loop free of any knowledge about
what the work actually is — Phase 3 registers graph execution here without touching the
loop.

**Every handler must be idempotent.** The queue guarantees at-least-once delivery: a
worker that dies mid-job leaves a lease that expires, and another worker reclaims it.
A handler that is not safe to run twice will eventually run twice.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from factory_core.domain.ids import ProjectId, RunId
from factory_core.events import EventPublisher, NewEvent
from factory_core.events.schemas import EventActor, ProgressPayload
from factory_core.events.types import EventType
from factory_core.infrastructure.queue import Job
from factory_core.observability import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class JobContext:
    """What a handler is given besides the job itself.

    ``publisher`` records events durably; the worker publishes them after the
    transaction commits, so a handler never has to think about the ordering.
    """

    publisher: EventPublisher
    worker_id: str


#: A handler's signature.
JobHandler = Callable[[Job, JobContext], Awaitable[None]]


class HandlerRegistry:
    """Maps job types to their handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}

    def register(self, job_type: str, handler: JobHandler) -> None:
        """Register a handler.

        Raises:
            ValueError: The type already has one. Silently replacing would make
                behaviour depend on import order.
        """
        if job_type in self._handlers:
            msg = f"a handler is already registered for job type {job_type!r}"
            raise ValueError(msg)
        self._handlers[job_type] = handler

    def get(self, job_type: str) -> JobHandler | None:
        """Look up a handler, or ``None`` if the type is unknown."""
        return self._handlers.get(job_type)

    @property
    def known_types(self) -> frozenset[str]:
        """Every registered job type."""
        return frozenset(self._handlers)


class UnknownJobTypeError(Exception):
    """No handler is registered for a claimed job's type.

    Treated as a job failure rather than a worker crash: a job enqueued by a newer
    revision must not take down a worker running an older one.
    """


async def handle_noop(job: Job, context: JobContext) -> None:
    """The Phase 2 pipeline proof.

    Does no real work. It exists to demonstrate the whole chain end to end — enqueue,
    claim under SKIP LOCKED, execute, persist events with per-run sequence numbers,
    publish through Redis, fan out to a browser — before any agent exists to drive it.

    Idempotent because it has no side effects beyond appending events, and a replayed
    run simply appends more.
    """
    run_id, project_id = require_run(job)
    steps = int(job.payload.get("steps", 3))
    steps = max(1, min(steps, 10))

    for step in range(1, steps + 1):
        await context.publisher.record(
            NewEvent(
                type=EventType.JOB_PROGRESS,
                run_id=run_id,
                project_id=project_id,
                actor=EventActor.system(),
                payload=ProgressPayload(
                    message=f"Step {step} of {steps}",
                    fraction=step / steps,
                    job_id=job.id,
                ),
            )
        )
        # A brief pause so a browser observes the steps arriving separately rather than
        # as one burst. Short enough not to hold the lease.
        await asyncio.sleep(0.05)

    logger.info("job.noop_completed", job_id=str(job.id), steps=steps)


def build_registry() -> HandlerRegistry:
    """Build the registry with every handler this worker knows.

    One place to see what a worker can execute. Phase 3 adds graph execution here.
    """
    registry = HandlerRegistry()
    registry.register("noop", handle_noop)
    return registry


def require_run(job: Job) -> tuple[RunId, ProjectId]:
    """Return a job's run and project ids, failing the job if either is absent.

    Both are nullable on the row because maintenance jobs belong to neither. A job that
    emits events needs both, so this converts "malformed job" into a typed failure the
    claim loop records against the job rather than a crash in the handler.

    Raises:
        ValueError: The job has no run or no project.
    """
    if job.run_id is None or job.project_id is None:
        msg = f"job {job.id} has no run_id/project_id and cannot emit events"
        raise ValueError(msg)
    return RunId(job.run_id), ProjectId(job.project_id)
