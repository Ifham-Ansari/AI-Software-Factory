"""Persist-then-publish, and what happens when Redis is down [F-210].

Acceptance criterion 6: *with Redis stopped, jobs still run to completion and events are
still persisted*. That is exactly what these tests drive — against a real database and a
Redis that raises on every call, because "Redis absent" and "Redis failing" take different
branches and only the second one is the outage being claimed.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from factory_core.domain.ids import ProjectId, new_id, new_project_id, new_run_id, new_user_id
from factory_core.errors import NotFoundError
from factory_core.events import EventPublisher, EventStore, NewEvent, create_run
from factory_core.events.schemas import EventActor, LogPayload, channel_for_run
from factory_core.events.types import EventType
from factory_core.infrastructure.redis import EventBus, RedisGateway
from factory_core.persistence import ProjectRepository, UserRepository
from factory_core.testing import BrokenRedis, FakeRedis

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
        name="Publisher",
        slug=f"pub-{new_id().hex[:8]}",
        description="",
    )
    return project.id


def _event(run_id: object, project_id: ProjectId, message: str) -> NewEvent:
    return NewEvent(
        type=EventType.RUN_LOG,
        run_id=run_id,  # type: ignore[arg-type]
        project_id=project_id,
        actor=EventActor.system(),
        payload=LogPayload(message=message),
    )


class TestPersistThenPublish:
    async def test_recording_persists_before_any_publish(self, session: AsyncSession) -> None:
        """The event must be durable before anyone is told about it."""
        project_id = await _make_project(session)
        run_id = new_run_id()
        await create_run(session, project_id=project_id, run_id=run_id)
        fake = FakeRedis()
        store = EventStore(session)
        publisher = EventPublisher(store, EventBus(RedisGateway(fake)))  # type: ignore[arg-type]

        await publisher.record(_event(run_id, project_id, "hello"))

        # Durable already; nothing published until the caller confirms the commit.
        assert len(await store.read_after(run_id)) == 1
        assert fake.published == []
        assert publisher.pending_count == 1

    async def test_publish_pending_fans_out_after_commit(self, session: AsyncSession) -> None:
        project_id = await _make_project(session)
        run_id = new_run_id()
        await create_run(session, project_id=project_id, run_id=run_id)
        fake = FakeRedis()
        publisher = EventPublisher(EventStore(session), EventBus(RedisGateway(fake)))  # type: ignore[arg-type]
        await publisher.record(_event(run_id, project_id, "hello"))

        delivered = await publisher.publish_pending()

        assert delivered == 1
        [(channel, message)] = fake.published
        assert channel == channel_for_run(run_id)
        assert "hello" in message
        assert publisher.pending_count == 0

    async def test_discarding_prevents_publication(self, session: AsyncSession) -> None:
        """Called when the transaction rolled back: announcing events no replay will
        return would be worse than saying nothing."""
        project_id = await _make_project(session)
        run_id = new_run_id()
        await create_run(session, project_id=project_id, run_id=run_id)
        fake = FakeRedis()
        publisher = EventPublisher(EventStore(session), EventBus(RedisGateway(fake)))  # type: ignore[arg-type]
        await publisher.record(_event(run_id, project_id, "doomed"))

        publisher.discard_pending()
        assert await publisher.publish_pending() == 0
        assert fake.published == []

    async def test_publishing_twice_does_not_duplicate(self, session: AsyncSession) -> None:
        """Pending events are drained, not copied — a second call is a no-op."""
        project_id = await _make_project(session)
        run_id = new_run_id()
        await create_run(session, project_id=project_id, run_id=run_id)
        fake = FakeRedis()
        publisher = EventPublisher(EventStore(session), EventBus(RedisGateway(fake)))  # type: ignore[arg-type]
        await publisher.record(_event(run_id, project_id, "once"))

        await publisher.publish_pending()
        await publisher.publish_pending()

        assert len(fake.published) == 1


@pytest.mark.failure
class TestRedisOutage:
    async def test_events_are_still_persisted_when_redis_errors(
        self, session: AsyncSession
    ) -> None:
        """Acceptance criterion 6. Redis is a latency optimisation; Postgres is truth."""
        project_id = await _make_project(session)
        run_id = new_run_id()
        await create_run(session, project_id=project_id, run_id=run_id)
        broken = BrokenRedis()
        store = EventStore(session)
        publisher = EventPublisher(store, EventBus(RedisGateway(broken)))  # type: ignore[arg-type]

        await publisher.record(_event(run_id, project_id, "during the outage"))
        delivered = await publisher.publish_pending()

        assert delivered == 0, "nothing could be published"
        assert broken.attempts > 0, "the publisher did not actually try Redis"
        # The point: durable and replayable regardless.
        replayed = await store.read_after(run_id)
        assert [e.payload.message for e in replayed] == ["during the outage"]  # type: ignore[union-attr]

    async def test_recording_never_raises_because_of_redis(self, session: AsyncSession) -> None:
        """A run must not fail because a *notification* could not be sent."""
        project_id = await _make_project(session)
        run_id = new_run_id()
        await create_run(session, project_id=project_id, run_id=run_id)
        publisher = EventPublisher(
            EventStore(session),
            EventBus(RedisGateway(BrokenRedis())),  # type: ignore[arg-type]
        )

        for i in range(3):
            await publisher.record(_event(run_id, project_id, f"line {i}"))
        await publisher.publish_pending()

        assert len(await EventStore(session).read_after(run_id)) == 3

    async def test_works_with_no_redis_configured_at_all(self, session: AsyncSession) -> None:
        """Running without Redis is a supported deployment, not a degraded one."""
        project_id = await _make_project(session)
        run_id = new_run_id()
        await create_run(session, project_id=project_id, run_id=run_id)
        publisher = EventPublisher(EventStore(session), EventBus(RedisGateway(None)))

        await publisher.record(_event(run_id, project_id, "no redis"))

        assert await publisher.publish_pending() == 0
        assert len(await EventStore(session).read_after(run_id)) == 1

    async def test_recording_into_a_missing_run_still_raises(self, session: AsyncSession) -> None:
        """Degrading on Redis must not have made real errors silent too."""
        project_id = await _make_project(session)
        publisher = EventPublisher(EventStore(session), EventBus(RedisGateway(FakeRedis())))  # type: ignore[arg-type]

        with pytest.raises(NotFoundError):
            await publisher.record(_event(new_run_id(), project_id, "orphan"))
