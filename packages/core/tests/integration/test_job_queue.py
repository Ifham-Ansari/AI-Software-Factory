"""Durable job queue against a real database [F-213].

``SKIP LOCKED`` behaviour cannot be tested with a fake — the whole point is what Postgres
does when two transactions contend for the same row. These tests use separate sessions so
the concurrency is real.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from factory_core.domain.ids import JobId, ProjectId, new_id, new_project_id, new_user_id
from factory_core.infrastructure.queue import JobQueue, JobRequest, JobStatus, backoff_seconds
from factory_core.persistence import ProjectRepository, UserRepository, create_session_factory

pytestmark = pytest.mark.integration


async def _make_project(session: AsyncSession) -> ProjectId:
    user = await UserRepository(session).create(
        user_id=new_user_id(),
        email=f"owner-{new_id().hex[:8]}@example.com",
        display_name="Owner",
        password_hash="$argon2id$fake",
    )
    project = await ProjectRepository(session, owner_id=user.id).create(
        project_id=new_project_id(),
        name="Queue",
        slug=f"queue-{new_id().hex[:8]}",
        description="",
    )
    return project.id


class TestEnqueueAndClaim:
    async def test_claim_returns_an_enqueued_job(self, session: AsyncSession) -> None:
        queue = JobQueue(session)
        job_id = await queue.enqueue(JobRequest(type="noop", payload={"steps": 2}))

        claimed = await queue.claim(worker_id="worker-1")

        assert claimed is not None
        assert claimed.id == job_id
        assert claimed.attempts == 1
        assert claimed.payload == {"steps": 2}

    async def test_an_empty_queue_returns_none(self, session: AsyncSession) -> None:
        assert await JobQueue(session).claim(worker_id="worker-1") is None

    async def test_a_delayed_job_is_not_claimable_yet(self, session: AsyncSession) -> None:
        queue = JobQueue(session)
        await queue.enqueue(JobRequest(type="noop", delay_seconds=3600))

        assert await queue.claim(worker_id="worker-1") is None

    async def test_a_delayed_job_becomes_claimable(self, session: AsyncSession) -> None:
        queue = JobQueue(session)
        await queue.enqueue(JobRequest(type="noop", delay_seconds=60))

        later = datetime.now(UTC) + timedelta(seconds=120)

        assert await queue.claim(worker_id="worker-1", now=later) is not None

    async def test_claiming_marks_the_job_running_with_a_lease(self, session: AsyncSession) -> None:
        queue = JobQueue(session)
        job_id = await queue.enqueue(JobRequest(type="noop"))

        await queue.claim(worker_id="worker-1", lease_seconds=30)

        row = await queue.get(job_id)
        assert row is not None
        assert row.status == JobStatus.RUNNING.value
        assert row.locked_by == "worker-1"
        assert row.lease_expires_at is not None


class TestIdempotency:
    async def test_duplicate_key_returns_the_same_job(self, session: AsyncSession) -> None:
        """Two submissions of the same logical work collapse to one row."""
        queue = JobQueue(session)
        key = f"deploy-{new_id().hex[:8]}"

        first = await queue.enqueue(JobRequest(type="noop", idempotency_key=key))
        second = await queue.enqueue(JobRequest(type="noop", idempotency_key=key))

        assert first == second
        assert await queue.count_by_status(JobStatus.PENDING) == 1

    async def test_jobs_without_a_key_are_independent(self, session: AsyncSession) -> None:
        """A null idempotency key must not collide with another null."""
        queue = JobQueue(session)

        first = await queue.enqueue(JobRequest(type="noop"))
        second = await queue.enqueue(JobRequest(type="noop"))

        assert first != second
        assert await queue.count_by_status(JobStatus.PENDING) == 2


@pytest.mark.security
class TestConcurrentClaims:
    async def test_each_job_is_claimed_exactly_once(self, engine: AsyncEngine) -> None:
        """The acceptance criterion for F-213.

        Five workers race for five jobs across separate transactions. ``SKIP LOCKED``
        must give each worker a different job — no duplicates, none missed.
        """
        factory = create_session_factory(engine)
        async with factory() as setup:
            for _ in range(5):
                await JobQueue(setup).enqueue(JobRequest(type="noop"))
            await setup.commit()

        async def claim(worker: int) -> str | None:
            async with factory() as own_session:
                job = await JobQueue(own_session).claim(worker_id=f"worker-{worker}")
                await own_session.commit()
                return str(job.id) if job else None

        claimed = await asyncio.gather(*(claim(i) for i in range(5)))
        ids = [job_id for job_id in claimed if job_id is not None]

        assert len(ids) == 5, "some workers came away empty"
        assert len(set(ids)) == 5, "the same job was claimed twice"

    async def test_more_workers_than_jobs_leaves_some_empty_handed(
        self, engine: AsyncEngine
    ) -> None:
        """SKIP LOCKED means a worker gets nothing rather than blocking."""
        factory = create_session_factory(engine)
        async with factory() as setup:
            await JobQueue(setup).enqueue(JobRequest(type="noop"))
            await setup.commit()

        async def claim(worker: int) -> str | None:
            async with factory() as own_session:
                job = await JobQueue(own_session).claim(worker_id=f"worker-{worker}")
                await own_session.commit()
                return str(job.id) if job else None

        claimed = await asyncio.gather(*(claim(i) for i in range(4)))

        assert len([j for j in claimed if j is not None]) == 1


@pytest.mark.failure
class TestLeasesAndRecovery:
    async def test_an_expired_lease_is_reclaimed(self, session: AsyncSession) -> None:
        """The crash-recovery path: a dead worker's job must not be stranded."""
        queue = JobQueue(session)
        job_id = await queue.enqueue(JobRequest(type="noop"))
        await queue.claim(worker_id="doomed-worker", lease_seconds=10)

        after_expiry = datetime.now(UTC) + timedelta(seconds=60)
        reclaimed = await queue.claim(worker_id="healthy-worker", now=after_expiry)

        assert reclaimed is not None
        assert reclaimed.id == job_id
        assert reclaimed.attempts == 2

    async def test_a_live_lease_is_not_reclaimed(self, session: AsyncSession) -> None:
        queue = JobQueue(session)
        await queue.enqueue(JobRequest(type="noop"))
        await queue.claim(worker_id="busy-worker", lease_seconds=300)

        assert await queue.claim(worker_id="other-worker") is None

    async def test_renewal_requires_ownership(self, session: AsyncSession) -> None:
        """A worker that lost its claim must learn so and stop."""
        queue = JobQueue(session)
        job_id = await queue.enqueue(JobRequest(type="noop"))
        await queue.claim(worker_id="owner-worker")

        assert await queue.renew_lease(JobId(job_id), worker_id="owner-worker")
        assert not await queue.renew_lease(JobId(job_id), worker_id="impostor")


@pytest.mark.failure
class TestRetryAndDeadLetter:
    async def test_a_failure_schedules_a_retry(self, session: AsyncSession) -> None:
        queue = JobQueue(session)
        job_id = await queue.enqueue(JobRequest(type="noop", max_attempts=3))
        await queue.claim(worker_id="worker-1")

        status = await queue.fail(JobId(job_id), error="boom")

        assert status is JobStatus.PENDING
        row = await queue.get(job_id)
        assert row is not None
        assert row.last_error == "boom"
        assert row.locked_by is None

    async def test_exhausted_attempts_dead_letter(self, session: AsyncSession) -> None:
        """A job that gives up must be distinguishable from one that will retry."""
        queue = JobQueue(session)
        job_id = await queue.enqueue(JobRequest(type="noop", max_attempts=2))

        await queue.claim(worker_id="w")
        assert await queue.fail(JobId(job_id), error="first") is JobStatus.PENDING

        # Backoff pushes run_after forward, so claim from a later moment.
        later = datetime.now(UTC) + timedelta(seconds=30)
        await queue.claim(worker_id="w", now=later)
        assert await queue.fail(JobId(job_id), error="second") is JobStatus.DEAD

        assert await queue.count_by_status(JobStatus.DEAD) == 1

    async def test_a_dead_job_is_never_claimed_again(self, session: AsyncSession) -> None:
        queue = JobQueue(session)
        job_id = await queue.enqueue(JobRequest(type="noop", max_attempts=1))
        await queue.claim(worker_id="w")
        await queue.fail(JobId(job_id), error="fatal")

        far_future = datetime.now(UTC) + timedelta(days=1)
        assert await queue.claim(worker_id="w", now=far_future) is None

    async def test_backoff_grows_and_is_capped(self) -> None:
        assert backoff_seconds(0) == 0.0
        assert backoff_seconds(1) < backoff_seconds(3)
        assert backoff_seconds(100) == 300.0

    async def test_completion_clears_the_claim(self, session: AsyncSession) -> None:
        queue = JobQueue(session)
        job_id = await queue.enqueue(JobRequest(type="noop"))
        await queue.claim(worker_id="w")

        await queue.complete(JobId(job_id))

        row = await queue.get(job_id)
        assert row is not None
        assert row.status == JobStatus.COMPLETED.value
        assert row.locked_by is None
        assert row.completed_at is not None
