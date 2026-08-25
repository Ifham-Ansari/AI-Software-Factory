"""ORM models for workflow runs, their event stream, and the durable job queue.

These three tables carry the platform's execution record. Two of their design details are
load-bearing and easy to get wrong:

**`workflow_events.seq` is per-run and gapless.** It is the replay cursor a reconnecting
browser sends back, so it must be dense and unique within a run. It is assigned by the
event store under a row lock on the parent run rather than by a sequence — a Postgres
sequence is global and skips on rollback, and a client asking for "everything after 41"
must not be told about a 42 that never existed.

**`jobs` is claimed with `FOR UPDATE SKIP LOCKED`.** The partial index on
`(status, run_after)` is what keeps that claim a cheap index scan as the completed-job
table grows.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from factory_core.persistence.base import Base, TimestampMixin, uuid_pk
from factory_core.persistence.models import JsonDict


class WorkflowRunRow(Base, TimestampMixin):
    """One execution of a workflow against a project.

    Phase 2 creates runs only to anchor events and jobs; the graph that populates them
    arrives in Phase 3. ``last_seq`` is the high-water mark used to assign the next
    event's sequence number.
    """

    __tablename__ = "workflow_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    #: Highest sequence number assigned to an event of this run.
    last_seq: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_workflow_runs_project_id_created_at", "project_id", "created_at"),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="status_valid",
        ),
        CheckConstraint("last_seq >= 0", name="last_seq_non_negative"),
    )


class WorkflowEventRow(Base):
    """One durable event in a run's stream.

    Append-only. No ``updated_at``: an event that could be edited would make the replay
    a client already received disagree with the one it would get now.
    """

    __tablename__ = "workflow_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonDict, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        # The replay contract: unique per run, and the index that serves `?after_seq=`.
        UniqueConstraint("run_id", "seq", name="uq_workflow_events_run_id_seq"),
        Index("ix_workflow_events_project_id_occurred_at", "project_id", "occurred_at"),
        CheckConstraint("seq > 0", name="seq_positive"),
    )


class JobRow(Base, TimestampMixin):
    """One unit of durable background work.

    A job is claimed by setting ``status='running'`` with a lease. If the worker dies the
    lease expires and another worker reclaims it — which is why every handler must be
    idempotent, and why ``idempotency_key`` exists to make "already did this" cheap to
    detect.
    """

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = uuid_pk()
    #: Nullable: not every job belongs to a project (maintenance sweeps do not).
    project_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    payload: Mapped[dict[str, Any]] = mapped_column(JsonDict, nullable=False, default=dict)

    #: Earliest time this job may be claimed. Backoff moves it forward.
    run_after: Mapped[datetime] = mapped_column(nullable=False)
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(nullable=False, default=5)

    #: Identifies the worker holding the claim, and until when.
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)

    #: Set once, on first enqueue, to collapse duplicate submissions.
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        # Two enqueues of the same logical work collapse to one row.
        UniqueConstraint("idempotency_key", name="uq_jobs_idempotency_key"),
        # The claim loop's access path: pending jobs whose time has come, oldest first.
        Index("ix_jobs_status_run_after", "status", "run_after"),
        # Reclaiming abandoned work scans running jobs by lease expiry.
        Index("ix_jobs_status_lease_expires_at", "status", "lease_expires_at"),
        Index("ix_jobs_project_id_created_at", "project_id", "created_at"),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'dead')",
            name="status_valid",
        ),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
    )
