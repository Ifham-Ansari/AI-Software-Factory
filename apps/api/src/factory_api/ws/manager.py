"""WebSocket connection management and Redis fan-out.

One process holds many sockets. An event produced anywhere in the cluster has to reach
every socket watching that run, including sockets on other replicas — which is what the
Redis subscription is for.

The design deliberately keeps two things separate:

* **Local delivery.** :meth:`ConnectionManager.broadcast` pushes to sockets on this
  process. It is what the Redis listener calls, and it is directly testable without Redis.
* **Cluster delivery.** :func:`run_fanout` subscribes to Redis and calls ``broadcast``.
  With no Redis, it simply never runs — sockets on the producing replica still work, and
  every client still recovers the full stream by replaying over REST.

**Backpressure**: a slow client must not stall the fan-out for everyone. Each send is
bounded by a timeout, and a socket that cannot keep up is dropped. Dropping is safe
because the client reconnects and replays from its last sequence number — the durable
stream in Postgres is what makes an aggressive drop policy acceptable.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict

from starlette.websockets import WebSocket, WebSocketState

from factory_core.domain.ids import RunId
from factory_core.events.schemas import channel_for_run
from factory_core.infrastructure.redis.pubsub import EventBus
from factory_core.observability import get_logger

logger = get_logger(__name__)

#: A send that takes longer than this means the client is not draining its buffer.
SEND_TIMEOUT_SECONDS = 5.0


class ConnectionManager:
    """Tracks live sockets per run and delivers messages to them."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def register(self, run_id: RunId, socket: WebSocket) -> None:
        """Start delivering a run's events to a socket."""
        async with self._lock:
            self._connections[str(run_id)].add(socket)
        logger.info("ws.connected", run_id=str(run_id), connections=self.count(run_id))

    async def unregister(self, run_id: RunId, socket: WebSocket) -> None:
        """Stop delivering to a socket, and forget the run once it has none."""
        key = str(run_id)
        async with self._lock:
            self._connections[key].discard(socket)
            if not self._connections[key]:
                del self._connections[key]
        logger.info("ws.disconnected", run_id=key)

    def count(self, run_id: RunId) -> int:
        """How many sockets on this process are watching a run."""
        return len(self._connections.get(str(run_id), ()))

    @property
    def total_connections(self) -> int:
        """Every socket this process holds. For diagnostics."""
        return sum(len(sockets) for sockets in self._connections.values())

    async def broadcast(self, run_id: RunId, message: str) -> int:
        """Send one message to every socket on this process watching a run.

        Returns:
            How many sockets received it. Sockets that error or time out are dropped;
            the client will reconnect and replay, so this never raises.
        """
        async with self._lock:
            targets = list(self._connections.get(str(run_id), ()))
        if not targets:
            return 0

        delivered = 0
        casualties: list[WebSocket] = []
        for socket in targets:
            if await self._send(socket, message):
                delivered += 1
            else:
                casualties.append(socket)

        for socket in casualties:
            await self.unregister(run_id, socket)
        return delivered

    @staticmethod
    async def _send(socket: WebSocket, message: str) -> bool:
        """Send with a timeout. Returns whether the socket is still usable."""
        if socket.client_state is not WebSocketState.CONNECTED:
            return False
        try:
            await asyncio.wait_for(socket.send_text(message), timeout=SEND_TIMEOUT_SECONDS)
        except TimeoutError:
            # Backpressure: the client is not draining. Drop it rather than let one slow
            # consumer hold up delivery to everyone else.
            logger.warning("ws.send_timeout")
            return False
        except (RuntimeError, OSError):
            # Socket closed underneath us. Normal, and not worth a warning.
            return False
        return True


async def run_fanout(manager: ConnectionManager, bus: EventBus, run_id: RunId) -> None:
    """Forward a run's Redis messages to local sockets until cancelled.

    Cancellation is the normal exit path — the caller cancels this task when the last
    socket for the run disconnects — so ``CancelledError`` is suppressed rather than
    logged as a failure.
    """
    if not bus.is_available:
        return
    channel = channel_for_run(run_id)
    with contextlib.suppress(asyncio.CancelledError):
        try:
            async with bus.subscribe(channel) as messages:
                async for message in messages:
                    await manager.broadcast(run_id, message)
        except Exception as exc:
            # A fan-out failure degrades liveness only: the events are durable and the
            # client recovers them by replaying. It must never take the socket down.
            logger.warning("ws.fanout_failed", run_id=str(run_id), error=type(exc).__name__)
