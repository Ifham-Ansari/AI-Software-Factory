"""The durable job queue.

Postgres, not a broker. The rationale is recorded in plan.md §13: our volume is orders of
magnitude below where a broker earns its operational cost, and enqueueing inside the same
transaction as the state change that caused it removes the dual-write problem entirely —
there is no window where a job exists but the thing it refers to does not.

The claim is the interesting part:

```sql
SELECT ... FROM jobs
WHERE status = 'pending' AND run_after <= now()
ORDER BY run_after
FOR UPDATE SKIP LOCKED
LIMIT 1
```

``SKIP LOCKED`` is what makes concurrent workers safe. Without it, every worker queues
behind the same row lock and the pool serialises; with it, each worker takes a different
row and contention disappears. This is the standard Postgres queue pattern, and the
``(status, run_after)`` index is what keeps it an index scan as completed jobs accumulate.

Crash safety comes from leases rather than transactions: a claim commits immediately with
a lease expiry, so a worker that dies leaves a row whose lease lapses and which another
worker reclaims. That is also why handlers must be idempotent — at-least-once delivery is
the guarantee, and exactly-once is not available.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from factory_core.domain.ids import JobId, new_job_id
from factory_core.infrastructure.queue.schemas import (
    Job,
    JobRequest,
    JobStatus,
    backoff_seconds,
)
from factory_core.persistence.models_runtime import JobRow


class JobQueue:
    """Enqueues, claims and completes durable jobs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, request: JobRequest, *, now: datetime | None = None) -> JobId:
        """Add a job, or return the existing one when its idempotency key is taken.

        Deduplication is enforced by a unique constraint rather than a pre-check, because
        a check-then-insert races: two concurrent enqueues both find nothing and both
        insert. Catching the violation is the only way to be correct under concurrency.
        """
        moment = now or datetime.now(UTC)
        if request.idempotency_key:
            existing = await self._find_by_key(request.idempotency_key)
            if existing is not None:
                return JobId(existing)

        job_id = new_job_id()
        row = JobRow(
            id=job_id,
            project_id=request.project_id,
            run_id=request.run_id,
            type=request.type,
            status=JobStatus.PENDING.value,
            payload=request.payload,
            run_after=moment + timedelta(seconds=request.delay_seconds),
            attempts=0,
            max_attempts=request.max_attempts,
            idempotency_key=request.idempotency_key,
            created_at=moment,
            updated_at=moment,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError:
            # Lost the race to another enqueue of the same key. Its row is the winner.
            await self._session.rollback()
            if request.idempotency_key:
                existing = await self._find_by_key(request.idempotency_key)
                if existing is not None:
                    return JobId(existing)
            raise
        return job_id

    async def claim(
        self, *, worker_id: str, lease_seconds: float = 60.0, now: datetime | None = None
    ) -> Job | None:
        """Claim the next due job for this worker, or ``None`` if there is nothing to do.

        Also reclaims jobs whose lease has expired — that is the crash-recovery path, and
        folding it into the same query means a dead worker's job is picked up on the very
        next poll rather than by a separate sweeper.
        """
        moment = now or datetime.now(UTC)
        statement = (
            select(JobRow)
            .where(
                or_(
                    (JobRow.status == JobStatus.PENDING.value) & (JobRow.run_after <= moment),
                    # A running job whose holder stopped renewing is abandoned.
                    (JobRow.status == JobStatus.RUNNING.value)
                    & (JobRow.lease_expires_at.is_not(None))
                    & (JobRow.lease_expires_at <= moment),
                )
            )
            .order_by(JobRow.run_after)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()
        if row is None:
            return None

        row.status = JobStatus.RUNNING.value
        row.attempts += 1
        row.locked_by = worker_id
        row.lease_expires_at = moment + timedelta(seconds=lease_seconds)
        row.updated_at = moment
        await self._session.flush()
        return _to_job(row)

    async def renew_lease(
        self, job_id: JobId, *, worker_id: str, lease_seconds: float = 60.0
    ) -> bool:
        """Extend a lease, only if this worker still holds it.

        Returns ``False`` when ownership was lost — the handler should stop, because
        another worker has already reclaimed the job and continuing would duplicate work.
        """
        moment = datetime.now(UTC)
        statement = (
            update(JobRow)
            .where(
                JobRow.id == job_id,
                JobRow.locked_by == worker_id,
                JobRow.status == JobStatus.RUNNING.value,
            )
            .values(
                lease_expires_at=moment + timedelta(seconds=lease_seconds),
                updated_at=moment,
            )
        )
        result = await self._session.execute(statement)
        # `execute` is typed as returning Result; an UPDATE always yields a
        # CursorResult, which is the only variant carrying rowcount.
        return bool(cast("CursorResult[Any]", result).rowcount)

    async def complete(self, job_id: JobId, *, now: datetime | None = None) -> None:
        """Mark a job finished."""
        moment = now or datetime.now(UTC)
        await self._session.execute(
            update(JobRow)
            .where(JobRow.id == job_id)
            .values(
                status=JobStatus.COMPLETED.value,
                completed_at=moment,
                locked_by=None,
                lease_expires_at=None,
                last_error=None,
                updated_at=moment,
            )
        )

    async def fail(self, job_id: JobId, *, error: str, now: datetime | None = None) -> JobStatus:
        """Record a failure, scheduling a retry or dead-lettering.

        Returns:
            The resulting status — ``PENDING`` when it will be retried, ``DEAD`` when
            attempts are exhausted.
        """
        moment = now or datetime.now(UTC)
        row = await self._session.get(JobRow, job_id)
        if row is None:
            return JobStatus.DEAD

        # Error text can echo a provider message; truncate so one pathological failure
        # cannot bloat the row, and never log it here.
        row.last_error = error[:2000]
        row.locked_by = None
        row.lease_expires_at = None
        row.updated_at = moment

        if row.attempts >= row.max_attempts:
            row.status = JobStatus.DEAD.value
        else:
            row.status = JobStatus.PENDING.value
            row.run_after = moment + timedelta(seconds=backoff_seconds(row.attempts))
        await self._session.flush()
        return JobStatus(row.status)

    async def get(self, job_id: JobId) -> JobRow | None:
        """Fetch a job row. Used by tests and operator tooling."""
        return await self._session.get(JobRow, job_id)

    async def count_by_status(self, status: JobStatus) -> int:
        """How many jobs are in a given state."""
        statement = select(func.count()).select_from(JobRow).where(JobRow.status == status.value)
        result = await self._session.execute(statement)
        return int(result.scalar_one())

    async def _find_by_key(self, key: str) -> uuid.UUID | None:
        statement = select(JobRow.id).where(JobRow.idempotency_key == key)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()


def _to_job(row: JobRow) -> Job:
    """Map a claimed row onto the value a handler receives."""
    return Job(
        id=row.id,
        type=row.type,
        payload=dict(row.payload),
        project_id=row.project_id,
        run_id=row.run_id,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        lease_expires_at=row.lease_expires_at,
    )
