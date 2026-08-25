"""Worker failure handling [F-214].

Split from ``test_processor.py`` (the success path) because these are the paths that keep
a worker alive: a handler that throws, a job type this revision has never heard of, and a
job missing the run its handler needs. None of them may crash the worker — each is
recorded against the job so it can be retried or dead-lettered.

The last test is the subtle one: events recorded by a handler that then fails must be
neither persisted nor published, because the transaction that produced them rolled back.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from factory_core.config import DatabaseSettings
from factory_core.domain.ids import JobId, new_id, new_project_id, new_run_id, new_user_id
from factory_core.events import EventStore, create_run
from factory_core.infrastructure.queue import Job, JobQueue, JobRequest, JobStatus
from factory_core.infrastructure.redis import EventBus, RedisGateway
from factory_core.persistence import (
    Base,
    ProjectRepository,
    UserRepository,
    create_engine,
    create_session_factory,
    unit_of_work,
)
from factory_core.testing import FakeRedis
from factory_worker.handlers import HandlerRegistry, JobContext, build_registry
from factory_worker.processor import JobProcessor

pytestmark = pytest.mark.integration

_schema_ready = False


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """An engine over a clean schema, matching the core integration fixture."""
    global _schema_ready
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")

    test_engine = create_engine(
        DatabaseSettings(url=url),  # type: ignore[arg-type]
        application_name="worker-tests",
    )
    async with test_engine.begin() as connection:
        if not _schema_ready:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
            _schema_ready = True
        else:
            tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
            await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield test_engine
    await test_engine.dispose()


async def _seed_run(engine: AsyncEngine) -> tuple[object, object]:
    """Create a project and a run, committed. Returns (project_id, run_id)."""
    factory = create_session_factory(engine)
    async with unit_of_work(factory) as session:
        user = await UserRepository(session).create(
            user_id=new_user_id(),
            email=f"worker-{new_id().hex[:8]}@example.com",
            display_name="Worker Owner",
            password_hash="$argon2id$fake",
        )
        project = await ProjectRepository(session, owner_id=user.id).create(
            project_id=new_project_id(),
            name="Worker",
            slug=f"worker-{new_id().hex[:8]}",
            description="",
        )
        run_id = new_run_id()
        await create_run(session, project_id=project.id, run_id=run_id)
        return project.id, run_id


def _processor(engine: AsyncEngine, registry: HandlerRegistry, redis: object) -> JobProcessor:
    return JobProcessor(
        session_factory=create_session_factory(engine),
        registry=registry,
        event_bus=EventBus(RedisGateway(redis)),  # type: ignore[arg-type]
        worker_id="test-worker",
    )


@pytest.mark.failure
class TestFailureHandling:
    async def test_a_throwing_handler_fails_the_job_not_the_worker(
        self, engine: AsyncEngine
    ) -> None:
        project_id, run_id = await _seed_run(engine)
        factory = create_session_factory(engine)
        async with unit_of_work(factory) as session:
            job_id = await JobQueue(session).enqueue(
                JobRequest(type="explodes", project_id=project_id, run_id=run_id, max_attempts=3)
            )

        async def explode(_job: Job, _context: JobContext) -> None:
            msg = "handler blew up"
            raise RuntimeError(msg)

        registry = HandlerRegistry()
        registry.register("explodes", explode)
        processor = _processor(engine, registry, FakeRedis())

        job = await processor.claim_one()
        assert job is not None
        result = await processor.process(job)

        assert result.status is JobStatus.PENDING, "should be retried"
        async with factory() as session:
            row = await JobQueue(session).get(JobId(job_id))
        assert row is not None
        assert "handler blew up" in (row.last_error or "")

    async def test_an_unknown_job_type_fails_the_job(self, engine: AsyncEngine) -> None:
        """A job enqueued by a newer revision must not crash an older worker."""
        project_id, run_id = await _seed_run(engine)
        factory = create_session_factory(engine)
        async with unit_of_work(factory) as session:
            await JobQueue(session).enqueue(
                JobRequest(type="from_the_future", project_id=project_id, run_id=run_id)
            )

        processor = _processor(engine, build_registry(), FakeRedis())
        job = await processor.claim_one()
        assert job is not None
        result = await processor.process(job)

        assert result.status is JobStatus.PENDING
        assert result.error is not None
        assert "UnknownJobTypeError" in result.error

    async def test_a_job_without_a_run_fails_cleanly(self, engine: AsyncEngine) -> None:
        """`noop` emits events, so it needs a run. Missing one is a job failure."""
        factory = create_session_factory(engine)
        async with unit_of_work(factory) as session:
            await JobQueue(session).enqueue(JobRequest(type="noop"))

        processor = _processor(engine, build_registry(), FakeRedis())
        job = await processor.claim_one()
        assert job is not None
        result = await processor.process(job)

        assert result.status is JobStatus.PENDING
        assert result.error is not None
        assert "ValueError" in result.error

    async def test_no_events_are_published_when_the_handler_fails(
        self, engine: AsyncEngine
    ) -> None:
        """The transaction rolled back, so announcing its events would be a lie."""
        project_id, run_id = await _seed_run(engine)
        factory = create_session_factory(engine)
        async with unit_of_work(factory) as session:
            await JobQueue(session).enqueue(
                JobRequest(type="emits_then_fails", project_id=project_id, run_id=run_id)
            )

        async def emit_then_fail(job: Job, context: JobContext) -> None:
            from factory_core.events import NewEvent
            from factory_core.events.schemas import LogPayload
            from factory_core.events.types import EventType

            await context.publisher.record(
                NewEvent(
                    type=EventType.RUN_LOG,
                    run_id=job.run_id,  # type: ignore[arg-type]
                    project_id=job.project_id,  # type: ignore[arg-type]
                    payload=LogPayload(message="about to fail"),
                )
            )
            msg = "after emitting"
            raise RuntimeError(msg)

        registry = HandlerRegistry()
        registry.register("emits_then_fails", emit_then_fail)
        fake = FakeRedis()
        processor = _processor(engine, registry, fake)

        job = await processor.claim_one()
        assert job is not None
        await processor.process(job)

        assert fake.published == [], "rolled-back events must not be published"
        async with factory() as session:
            events = await EventStore(session).read_after(run_id)  # type: ignore[arg-type]
        assert events == [], "the transaction rolled back"
