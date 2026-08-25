"""Redis pub/sub fan-out.

This is how an event reaches a browser connected to a *different* API replica than the one
that produced it. The replica that emits publishes to a channel; every replica holding a
socket for that run is subscribed and forwards to its own connections.

Pub/sub is fire-and-forget: a message published while nobody is subscribed is gone. That
is acceptable only because it is never the durable path — the event is already committed
to Postgres before it is published, and a client that missed something replays over REST
using its last sequence number. Redis buys latency; Postgres provides the guarantee.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from redis.exceptions import RedisError

from factory_core.infrastructure.redis.client import RedisGateway
from factory_core.observability import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from redis.asyncio.client import PubSub

logger = get_logger(__name__)

#: How long a single read waits before reporting "nothing yet" and waiting again.
#: Only bounds loop granularity — delivery is push, so this adds no latency to a message
#: that does arrive. Kept well under the connection's ``socket_timeout`` so the read never
#: reaches it.
IDLE_WAIT_SECONDS = 1.0


class EventBus:
    """Publishes and subscribes to event channels."""

    def __init__(self, gateway: RedisGateway) -> None:
        self._gateway = gateway

    @property
    def is_available(self) -> bool:
        """Whether fan-out is possible at all."""
        return self._gateway.is_available

    async def publish(self, channel: str, message: str) -> bool:
        """Publish one message.

        Returns:
            Whether the publish reached Redis. Callers log the ``False`` case rather than
            failing: the event is already durable, so a lost publish delays delivery
            until the client's next replay instead of losing it.
        """
        if not self._gateway.is_available:
            return False
        try:
            await self._gateway.client.publish(channel, message)
        except (RedisError, OSError) as exc:
            self._gateway.note_outage("publish", exc)
            return False
        self._gateway.note_recovery()
        return True

    @asynccontextmanager
    async def subscribe(self, *channels: str) -> AsyncIterator[AsyncIterator[str]]:
        """Subscribe to channels, yielding an iterator of message payloads.

        The subscription is torn down on exit even if the consumer raises, which matters
        because a leaked pub/sub connection holds a socket open for the life of the
        process.

        Raises:
            RedisUnavailableError: No Redis is configured. A caller wanting live updates
                without Redis has nothing to iterate, and silently yielding an empty
                stream would look like "no events happening".
        """
        pubsub = self._gateway.client.pubsub()
        try:
            await pubsub.subscribe(*channels)
            yield _messages(pubsub)
        finally:
            try:
                await pubsub.unsubscribe(*channels)
                # `aclose` is untyped in redis-py's stubs.
                await pubsub.aclose()  # type: ignore[no-untyped-call]
            except (RedisError, OSError) as exc:
                # Teardown failure must not mask whatever the consumer was doing.
                logger.debug("pubsub.teardown_failed", error=type(exc).__name__)


async def _messages(pubsub: PubSub) -> AsyncIterator[str]:
    """Yield payloads from a subscription, ignoring non-message frames.

    Redis delivers subscribe/unsubscribe confirmations on the same stream; only ``message``
    frames carry an event.

    **Why ``get_message`` and not ``listen()``.** ``listen()`` issues an unbounded blocking
    read, which the connection's ``socket_timeout`` then cuts short: on a channel with
    nothing published, the read raises ``TimeoutError`` after a few seconds and ends the
    subscription permanently. Runs are quiet most of the time, so that would silently kill
    fan-out on every socket shortly after it connected — the failure is invisible because
    the socket stays open and the client keeps replaying. ``get_message`` returns ``None``
    on timeout, which is the honest representation of "nothing published yet", and the loop
    simply waits again.
    """
    while True:
        frame = await pubsub.get_message(timeout=IDLE_WAIT_SECONDS)
        if frame is None:
            # Nothing published within the window. Not an error, and not a busy-wait:
            # the await above is what does the waiting.
            continue
        if frame.get("type") != "message":
            # Subscribe/unsubscribe confirmations share this stream, and so do the replies
            # to redis-py's periodic health-check PING — which arrive as ``pong`` frames
            # whose ``data`` is a string, and which ``ignore_subscribe_messages`` does not
            # filter. Without this check a keepalive would be forwarded to every browser
            # watching the run as though it were an event.
            continue
        data = frame.get("data")
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="replace")
        if isinstance(data, str):
            yield data
