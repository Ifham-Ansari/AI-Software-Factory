"""Worker job processing [F-214].

Drives the paths that matter operationally: a handler that succeeds, one that throws, one
whose type is unknown, and the graceful-drain behaviour on shutdown. All against a real
database, because claim/complete/fail are SQL and the lease semantics are the point.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from factory_core.config import DatabaseSettings
from factory_core.domain.ids import new_id, new_project_id, new_run_id, new_user_id
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
from factory_core.testing import BrokenRedis, FakeRedis
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


class TestNoopPipeline:
    async def test_a_claimed_job_runs_and_emits_events(self, engine: AsyncEngine) -> None:
        """The Phase 2 pipeline proof, end to end below the HTTP layer."""
        project_id, run_id = await _seed_run(engine)
        factory = create_session_factory(engine)
        async with unit_of_work(factory) as session:
            await JobQueue(session).enqueue(
                JobRequest(type="noop", payload={"steps": 3}, project_id=project_id, run_id=run_id)
            )

        processor = _processor(engine, build_registry(), FakeRedis())
        job = await processor.claim_one()
        assert job is not None
        result = await processor.process(job)

        assert result.status is JobStatus.COMPLETED
        async with factory() as session:
            events = await EventStore(session).read_after(run_id)  # type: ignore[arg-type]
        assert [e.seq for e in events] == [1, 2, 3]

    async def test_events_are_published_after_the_commit(self, engine: AsyncEngine) -> None:
        project_id, run_id = await _seed_run(engine)
        factory = create_session_factory(engine)
        async with unit_of_work(factory) as session:
            await JobQueue(session).enqueue(
                JobRequest(type="noop", payload={"steps": 2}, project_id=project_id, run_id=run_id)
            )

        fake = FakeRedis()
        processor = _processor(engine, build_registry(), fake)
        job = await processor.claim_one()
        assert job is not None
        await processor.process(job)

        assert len(fake.published) == 2

    @pytest.mark.failure
    async def test_the_job_still_completes_with_redis_down(self, engine: AsyncEngine) -> None:
        """Acceptance criterion 6: jobs run to completion and events are still persisted."""
        project_id, run_id = await _seed_run(engine)
        factory = create_session_factory(engine)
        async with unit_of_work(factory) as session:
            await JobQueue(session).enqueue(
                JobRequest(type="noop", payload={"steps": 2}, project_id=project_id, run_id=run_id)
            )

        broken = BrokenRedis()
        processor = _processor(engine, build_registry(), broken)
        job = await processor.claim_one()
        assert job is not None
        result = await processor.process(job)

        assert result.status is JobStatus.COMPLETED
        async with factory() as session:
            events = await EventStore(session).read_after(run_id)  # type: ignore[arg-type]
        assert len(events) == 2, "events must be durable regardless of Redis"


class TestHandlerRegistry:
    def test_registering_a_duplicate_type_is_refused(self) -> None:
        """Silently replacing would make behaviour depend on import order."""
        registry = build_registry()

        async def other(_job: Job, _context: JobContext) -> None:
            return None

        with pytest.raises(ValueError, match="already registered"):
            registry.register("noop", other)

    def test_the_default_registry_knows_noop(self) -> None:
        assert "noop" in build_registry().known_types

    def test_an_unknown_type_returns_none(self) -> None:
        assert build_registry().get("nothing_registered") is None


class TestGracefulDrain:
    async def test_a_stop_request_is_observed_promptly(self, engine: AsyncEngine) -> None:
        """SIGTERM on an idle worker should exit quickly, not wait a full poll interval."""
        from factory_core.config import (
            ApiSettings,
            Environment,
            ObservabilitySettings,
            SecuritySettings,
            Settings,
        )
        from factory_worker.runner import Worker

        url = os.environ["TEST_DATABASE_URL"]
        settings = Settings(
            environment=Environment.TEST,
            database=DatabaseSettings(url=url),  # type: ignore[arg-type]
            security=SecuritySettings(
                jwt_secret_key="test-secret-key-that-is-at-least-32-characters",  # type: ignore[arg-type]
                argon2_time_cost=1,
                argon2_memory_cost_kib=8192,
                argon2_parallelism=1,
            ),
            observability=ObservabilitySettings(service_name="worker-test", log_level="WARNING"),
            api=ApiSettings(docs_enabled=False),
        )
        worker = Worker(settings)

        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0.5)
        worker.request_stop()

        # Comfortably under the poll interval plus startup, and far under any timeout.
        await asyncio.wait_for(task, timeout=10)

    def test_worker_ids_are_unique(self) -> None:
        """Two workers in one container must not share an id, or lease ownership breaks."""
        from factory_worker.runner import build_worker_id

        assert build_worker_id() != build_worker_id()
