"""Job queue value types.

Kept apart from the repository so the worker's handler signatures do not drag SQLAlchemy
into their import graph, and so a handler can be unit-tested against a plain
:class:`Job` with no database in sight.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobStatus(StrEnum):
    """Where a job is in its lifecycle.

    ``FAILED`` is retryable — the job goes back to ``PENDING`` with backoff. ``DEAD`` is
    terminal: attempts are exhausted and a human needs to look. Keeping them distinct is
    what makes the dead-letter query "everything that gave up" rather than "everything
    that ever failed".
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"


class JobRequest(BaseModel):
    """A request to enqueue work."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    project_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    #: Collapses duplicate submissions of the same logical work.
    idempotency_key: str | None = Field(default=None, max_length=128)
    max_attempts: int = Field(default=5, ge=1, le=20)
    #: Delay before the job first becomes claimable.
    delay_seconds: int = Field(default=0, ge=0)


class Job(BaseModel):
    """A claimed unit of work, as handed to a handler."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    type: str
    payload: dict[str, Any]
    project_id: uuid.UUID | None
    run_id: uuid.UUID | None
    attempts: int
    max_attempts: int
    lease_expires_at: datetime | None

    @property
    def is_final_attempt(self) -> bool:
        """Whether failing now sends this job to the dead-letter state.

        Handlers use it to decide whether to emit a "giving up" event, and tests use it
        to drive the dead-letter path deliberately.
        """
        return self.attempts >= self.max_attempts


def backoff_seconds(attempts: int, *, base: float = 2.0, cap: float = 300.0) -> float:
    """Delay before retrying a job that has failed ``attempts`` times.

    Exponential with a cap. No jitter: this queue is claimed with ``SKIP LOCKED``, so
    workers waking together do not collide the way they would when contending for one
    row — they simply take different jobs. Jitter would buy nothing and make the retry
    schedule untestable.
    """
    if attempts < 1:
        return 0.0
    return min(cap, base ** min(attempts, 16))
