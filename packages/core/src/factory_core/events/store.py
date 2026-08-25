"""Durable event storage with per-run sequence numbers.

``seq`` is the replay contract. A reconnecting browser says "I have everything up to 41";
the server must be able to return 42, 43, 44 with no gaps and no repeats. That rules out
the two obvious implementations:

* A Postgres ``SEQUENCE`` is global and does not roll back. Two runs would interleave
  numbers, and an aborted transaction would burn one — leaving a permanent hole that a
  client can only interpret as a lost event.
* ``SELECT max(seq) + 1`` without a lock races. Two concurrent emits read the same max and
  both insert it; one loses to the unique constraint, and under retry the ordering is no
  longer the order things happened.

So the next number comes from ``workflow_runs.last_seq`` incremented under a row lock
(``SELECT ... FOR UPDATE``). Serialising per run is acceptable because events for one run
are already produced by one graph, and it makes the sequence dense by construction.

The lock is held for the duration of the enclosing transaction, so an event is only ever
visible to a reader once its sequence number is final.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from factory_core.domain.ids import ProjectId, RunId, UserId, new_event_id
from factory_core.errors import NotFoundError
from factory_core.events.schemas import EventEnvelope, NewEvent
from factory_core.events.types import ActorKind, EventType
from factory_core.persistence.models import ProjectRow
from factory_core.persistence.models_runtime import WorkflowEventRow, WorkflowRunRow

#: Replay is paginated so a client reconnecting to a very long run cannot ask the server
#: to materialise a million rows in one response.
MAX_REPLAY_LIMIT = 500


class EventStore:
    """Appends events to a run's stream and reads them back for replay."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """The session this store reads and writes through."""
        return self._session

    async def append(self, event: NewEvent) -> EventEnvelope:
        """Persist one event, assigning the next sequence number for its run.

        Raises:
            NotFoundError: The run does not exist. Emitting into a nonexistent run is a
                programming error, and creating the run implicitly would hide it.
        """
        run = await self._lock_run(RunId(event.run_id))

        next_seq = run.last_seq + 1
        run.last_seq = next_seq
        occurred_at = event.occurred_at or datetime.now(UTC)

        row = WorkflowEventRow(
            id=new_event_id(),
            run_id=event.run_id,
            project_id=event.project_id,
            seq=next_seq,
            type=event.type.value,
            actor_type=event.actor.kind.value,
            actor_id=event.actor.id,
            payload=event.payload.model_dump(mode="json"),
            occurred_at=occurred_at,
        )
        self._session.add(row)
        await self._session.flush()
        return to_envelope(row)

    async def read_after(
        self, run_id: RunId, *, after_seq: int = 0, limit: int = 100
    ) -> list[EventEnvelope]:
        """Read a run's events with ``seq`` greater than ``after_seq``.

        This is the replay path. Ordering is by ``seq`` because that is the order the
        client must reassemble them in — ``occurred_at`` has clock resolution ties.
        """
        capped = max(1, min(limit, MAX_REPLAY_LIMIT))
        statement = (
            select(WorkflowEventRow)
            .where(
                WorkflowEventRow.run_id == run_id,
                WorkflowEventRow.seq > max(0, after_seq),
            )
            .order_by(WorkflowEventRow.seq)
            .limit(capped)
        )
        result = await self._session.execute(statement)
        return [to_envelope(row) for row in result.scalars()]

    async def latest_seq(self, run_id: RunId) -> int:
        """Return the highest sequence number assigned for a run, or 0 if none."""
        statement = select(WorkflowRunRow.last_seq).where(WorkflowRunRow.id == run_id)
        result = await self._session.execute(statement)
        value = result.scalar_one_or_none()
        return int(value) if value is not None else 0

    async def is_owned_by(self, run_id: RunId, *, owner_id: UserId) -> bool:
        """Whether a run belongs to a project owned by this user.

        The authorization check behind every run-scoped route. Joining to ``projects``
        rather than trusting a caller-supplied project id is what stops a run id from
        being usable across accounts.
        """
        statement = (
            select(WorkflowRunRow.id)
            .join(ProjectRow, ProjectRow.id == WorkflowRunRow.project_id)
            .where(WorkflowRunRow.id == run_id, ProjectRow.owner_id == owner_id)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def project_for(self, run_id: RunId) -> ProjectId:
        """Return the project a run belongs to.

        Raises:
            NotFoundError: The run does not exist.
        """
        statement = select(WorkflowRunRow.project_id).where(WorkflowRunRow.id == run_id)
        result = await self._session.execute(statement)
        project_id = result.scalar_one_or_none()
        if project_id is None:
            raise NotFoundError("The requested run was not found.")
        return ProjectId(project_id)

    async def created_at(self, run_id: RunId) -> datetime:
        """Return when a run was created.

        Raises:
            NotFoundError: The run does not exist.
        """
        statement = select(WorkflowRunRow.created_at).where(WorkflowRunRow.id == run_id)
        result = await self._session.execute(statement)
        value = result.scalar_one_or_none()
        if value is None:
            raise NotFoundError("The requested run was not found.")
        return value

    async def _lock_run(self, run_id: RunId) -> WorkflowRunRow:
        """Take a row lock on the run so its ``last_seq`` can be advanced safely."""
        statement = select(WorkflowRunRow).where(WorkflowRunRow.id == run_id).with_for_update()
        result = await self._session.execute(statement)
        run = result.scalar_one_or_none()
        if run is None:
            raise NotFoundError("The requested run was not found.")
        return run


def to_envelope(row: WorkflowEventRow) -> EventEnvelope:
    """Map a stored row onto its wire representation.

    Validates on the way out as well as in. A row written by an older revision with a
    payload shape that no longer parses should fail loudly here rather than reach a
    browser as something the client cannot handle.
    """
    return EventEnvelope.model_validate(
        {
            "event_id": row.id,
            "seq": row.seq,
            "type": EventType(row.type),
            "run_id": row.run_id,
            "project_id": row.project_id,
            "occurred_at": row.occurred_at,
            "actor": {"kind": ActorKind(row.actor_type), "id": row.actor_id},
            "payload": row.payload,
        }
    )


async def create_run(session: AsyncSession, *, project_id: uuid.UUID, run_id: RunId) -> None:
    """Create a workflow run so events and jobs have something to hang from.

    Phase 2 needs runs to exist before the graph that would normally create them does.
    Kept here rather than in a service because it is a single insert with no policy.
    """
    session.add(
        WorkflowRunRow(
            id=run_id,
            project_id=project_id,
            status="pending",
            last_seq=0,
        )
    )
    await session.flush()
