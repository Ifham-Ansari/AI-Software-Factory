"""Persist-then-publish event publishing.

The order is the whole design:

1. ``INSERT`` into ``workflow_events``, which assigns the sequence number and makes the
   event durable.
2. ``PUBLISH`` to Redis so connected replicas can forward it immediately.

Never the reverse. Publishing first would let a client observe an event that a subsequent
rollback erases — and there is no way to un-send it. With this order the worst case is a
delay: the publish is lost, and the client picks the event up on its next replay.

**The publish happens after the transaction commits.** Publishing inside the transaction
would announce an event that could still roll back. The publisher therefore buffers
published events and flushes them when the caller confirms the commit, which is why
:meth:`EventPublisher.publish_pending` exists rather than the publish being inline.
"""

from __future__ import annotations

from factory_core.events.schemas import EventEnvelope, NewEvent, channel_for_run
from factory_core.events.store import EventStore
from factory_core.infrastructure.redis.pubsub import EventBus
from factory_core.observability import get_logger

logger = get_logger(__name__)


class EventPublisher:
    """Records events durably and fans them out after commit.

    One instance per unit of work (per request, per job). It holds the events appended
    during that unit so they can be published once the transaction that produced them is
    known to have committed.
    """

    def __init__(self, store: EventStore, bus: EventBus | None = None) -> None:
        self._store = store
        self._bus = bus
        self._pending: list[EventEnvelope] = []

    @property
    def pending_count(self) -> int:
        """How many events are awaiting publication. Used by tests and diagnostics."""
        return len(self._pending)

    async def record(self, event: NewEvent) -> EventEnvelope:
        """Persist an event and queue it for publication after commit.

        Raises:
            NotFoundError: The run does not exist.
        """
        envelope = await self._store.append(event)
        self._pending.append(envelope)
        return envelope

    async def publish_pending(self) -> int:
        """Publish every recorded event. Call only after the transaction has committed.

        Returns:
            How many events reached Redis. A shortfall is logged, not raised: the events
            are durable, and failing the caller's operation because a *notification*
            could not be sent would turn a Redis outage into a functional outage.
        """
        if not self._pending:
            return 0

        events, self._pending = self._pending, []
        if self._bus is None or not self._bus.is_available:
            return 0

        delivered = 0
        for envelope in events:
            message = envelope.model_dump_json()
            if await self._bus.publish(channel_for_run(envelope.run_id), message):
                delivered += 1

        if delivered < len(events):
            logger.warning(
                "events.publish_incomplete",
                recorded=len(events),
                delivered=delivered,
                # No payloads: an event body can carry user-supplied text.
                run_id=str(events[0].run_id),
            )
        return delivered

    def discard_pending(self) -> None:
        """Drop queued events without publishing.

        Called when the transaction rolled back. The rows are gone, so announcing them
        would tell clients about events that no replay will ever return.
        """
        if self._pending:
            logger.debug("events.discarded", count=len(self._pending))
            self._pending.clear()
