"""Event store sequencing and replay against a real database [F-209, F-212].

The acceptance criteria here are about ``seq``: gapless and unique per run, including
under concurrency, because it is the cursor a reconnecting browser replays from. A gap
would look to a client exactly like a lost event.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from factory_core.domain.ids import (
    ProjectId,
    RunId,
    UserId,
    new_id,
    new_project_id,
    new_run_id,
    new_user_id,
)
from factory_core.errors import NotFoundError
from factory_core.events import EventStore, NewEvent, create_run
from factory_core.events.schemas import EventActor, LogPayload
from factory_core.events.types import EventType
from factory_core.persistence import ProjectRepository, UserRepository, create_session_factory
from factory_core.persistence.models_runtime import WorkflowEventRow

pytestmark = pytest.mark.integration


async def _make_project(session: AsyncSession) -> tuple[UserId, ProjectId]:
    user = await UserRepository(session).create(
        user_id=new_user_id(),
        email=f"owner-{new_id().hex[:8]}@example.com",
        display_name="Owner",
        password_hash="$argon2id$fake",
    )
    project = await ProjectRepository(session, owner_id=user.id).create(
        project_id=new_project_id(),
        name="Events",
        slug=f"events-{new_id().hex[:8]}",
        description="",
    )
    return user.id, project.id


def _event(run_id: RunId, project_id: ProjectId, message: str) -> NewEvent:
    return NewEvent(
        type=EventType.RUN_LOG,
        run_id=run_id,
        project_id=project_id,
        actor=EventActor.system(),
        payload=LogPayload(message=message),
    )


class TestSequencing:
    async def test_sequences_start_at_one_and_are_dense(self, session: AsyncSession) -> None:
        _, project_id = await _make_project(session)
        run_id = new_run_id()
        await create_run(session, project_id=project_id, run_id=run_id)
        store = EventStore(session)

        seqs = [
            (await store.append(_event(run_id, project_id, f"line {i}"))).seq for i in range(1, 6)
        ]

        assert seqs == [1, 2, 3, 4, 5]

    async def test_sequences_are_independent_per_run(self, session: AsyncSession) -> None:
        """Two runs must not interleave numbers — a global sequence would."""
        _, project_id = await _make_project(session)
        first, second = new_run_id(), new_run_id()
        await create_run(session, project_id=project_id, run_id=first)
        await create_run(session, project_id=project_id, run_id=second)
        store = EventStore(session)

        await store.append(_event(first, project_id, "a"))
        await store.append(_event(first, project_id, "b"))
        second_seq = (await store.append(_event(second, project_id, "c"))).seq

        assert second_seq == 1

    @pytest.mark.failure
    async def test_appending_to_an_unknown_run_is_refused(self, session: AsyncSession) -> None:
        """Creating the run implicitly would hide a programming error."""
        _, project_id = await _make_project(session)

        with pytest.raises(NotFoundError):
            await EventStore(session).append(_event(new_run_id(), project_id, "orphan"))

    @pytest.mark.failure
    async def test_duplicate_sequence_is_rejected_by_the_database(
        self, session: AsyncSession
    ) -> None:
        """The unique constraint is the last line of defence behind the row lock."""
        _, project_id = await _make_project(session)
        run_id = new_run_id()
        await create_run(session, project_id=project_id, run_id=run_id)
        store = EventStore(session)
        await store.append(_event(run_id, project_id, "first"))

        session.add(
            WorkflowEventRow(
                id=new_id(),
                run_id=run_id,
                project_id=project_id,
                seq=1,
                type=EventType.RUN_LOG.value,
                actor_type="system",
                actor_id=None,
                payload={"kind": "log", "message": "duplicate", "level": "info"},
                occurred_at=(await store.read_after(run_id))[0].occurred_at,
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.security
class TestConcurrency:
    async def test_concurrent_appends_produce_no_gaps_or_duplicates(
        self, engine: AsyncEngine
    ) -> None:
        """The acceptance criterion for F-209.

        Five concurrent transactions append to the same run. The row lock on
        ``workflow_runs`` serialises them, so the result must be exactly 1..5 with no
        repeats — the property a client's replay cursor depends on.
        """
        factory = create_session_factory(engine)
        async with factory() as setup:
            _, project_id = await _make_project(setup)
            run_id = new_run_id()
            await create_run(setup, project_id=project_id, run_id=run_id)
            await setup.commit()

        async def append_one(index: int) -> int:
            async with factory() as own_session:
                store = EventStore(own_session)
                envelope = await store.append(_event(run_id, project_id, f"concurrent {index}"))
                await own_session.commit()
                return envelope.seq

        seqs = await asyncio.gather(*(append_one(i) for i in range(5)))

        assert sorted(seqs) == [1, 2, 3, 4, 5]


class TestReplay:
    async def test_read_after_returns_exactly_the_gap(self, session: AsyncSession) -> None:
        """The acceptance criterion for F-212: nothing lost, nothing duplicated."""
        _, project_id = await _make_project(session)
        run_id = new_run_id()
        await create_run(session, project_id=project_id, run_id=run_id)
        store = EventStore(session)
        for i in range(1, 6):
            await store.append(_event(run_id, project_id, f"line {i}"))

        gap = await store.read_after(run_id, after_seq=2)

        assert [e.seq for e in gap] == [3, 4, 5]

    async def test_replay_from_zero_returns_everything(self, session: AsyncSession) -> None:
        _, project_id = await _make_project(session)
        run_id = new_run_id()
        await create_run(session, project_id=project_id, run_id=run_id)
        store = EventStore(session)
        for i in range(3):
            await store.append(_event(run_id, project_id, f"line {i}"))

        assert len(await store.read_after(run_id, after_seq=0)) == 3

    async def test_replay_past_the_end_is_empty(self, session: AsyncSession) -> None:
        """A caught-up client must get an empty page, not an error."""
        _, project_id = await _make_project(session)
        run_id = new_run_id()
        await create_run(session, project_id=project_id, run_id=run_id)
        store = EventStore(session)
        await store.append(_event(run_id, project_id, "only"))

        assert await store.read_after(run_id, after_seq=99) == []

    async def test_limit_is_respected_and_ordered(self, session: AsyncSession) -> None:
        _, project_id = await _make_project(session)
        run_id = new_run_id()
        await create_run(session, project_id=project_id, run_id=run_id)
        store = EventStore(session)
        for i in range(10):
            await store.append(_event(run_id, project_id, f"line {i}"))

        page = await store.read_after(run_id, after_seq=0, limit=4)

        assert [e.seq for e in page] == [1, 2, 3, 4]

    async def test_payload_survives_the_round_trip(self, session: AsyncSession) -> None:
        _, project_id = await _make_project(session)
        run_id = new_run_id()
        await create_run(session, project_id=project_id, run_id=run_id)
        store = EventStore(session)
        await store.append(_event(run_id, project_id, "the message"))

        [restored] = await store.read_after(run_id)

        assert isinstance(restored.payload, LogPayload)
        assert restored.payload.message == "the message"


@pytest.mark.security
class TestOwnership:
    async def test_a_run_is_only_owned_by_its_projects_owner(self, session: AsyncSession) -> None:
        """What stops a run id from being usable across accounts."""
        owner, project_id = await _make_project(session)
        stranger, _ = await _make_project(session)
        run_id = new_run_id()
        await create_run(session, project_id=project_id, run_id=run_id)
        store = EventStore(session)

        assert await store.is_owned_by(run_id, owner_id=owner)
        assert not await store.is_owned_by(run_id, owner_id=stranger)

    async def test_unknown_run_is_owned_by_nobody(self, session: AsyncSession) -> None:
        owner, _ = await _make_project(session)

        assert not await EventStore(session).is_owned_by(new_run_id(), owner_id=owner)
