"""Cross-replica WebSocket fan-out [F-211].

Acceptance criterion: *two API replicas both receive a published event*.

A replica's whole share of live delivery is three objects — its own ``ConnectionManager``
holding its own sockets, its own ``EventBus`` over its own Redis connection, and its own
``run_fanout`` subscription. Nothing else in the API process takes part, so two independent
sets of those against one real Redis reproduce the cluster boundary exactly, and do it fast
enough to run on every commit rather than only in a job that boots two servers.

What this adds over ``test_pubsub_fanout.py`` in core is the API wiring: that ``run_fanout``
subscribes to the channel ``channel_for_run`` names, and that what arrives is handed to
``broadcast`` and reaches the sockets. A channel-name mismatch between publisher and
subscriber would pass every test on either side of it and still deliver nothing.

Real Redis is required; there is no fake subscription, on purpose. See the module docstring
of ``packages/core/tests/integration/test_pubsub_fanout.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
from starlette.websockets import WebSocketState

from factory_api.ws.manager import ConnectionManager, run_fanout
from factory_core.config.integrations import RedisSettings
from factory_core.domain.ids import new_run_id
from factory_core.events.schemas import channel_for_run
from factory_core.infrastructure.redis import EventBus, RedisGateway
from factory_core.infrastructure.redis.client import create_redis

pytestmark = pytest.mark.integration

SKIP_REASON = (
    "TEST_REDIS_URL is not set. Cross-replica fan-out needs a real Redis: the property "
    "under test is that one process's publish reaches another process's sockets."
)

#: How long to wait for one delivery attempt before publishing again.
ATTEMPT_SECONDS = 1.0

#: Overall budget for a payload to reach every socket.
RECEIVE_TIMEOUT = 30.0

#: How long to watch a socket that must stay silent.
QUIET_SECONDS = 3.0


class RecordingSocket:
    """A stand-in for a browser connection.

    ``ConnectionManager`` needs exactly two things from a socket — whether it is still
    connected, and somewhere to send text. Using the real ``WebSocket`` would drag in an
    ASGI server and prove nothing extra.
    """

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.client_state = WebSocketState.CONNECTED
        self.arrived = asyncio.Event()

    async def send_text(self, message: str) -> None:
        self.sent.append(message)
        self.arrived.set()

    async def wait_for(self, payload: str, budget: float) -> bool:
        """Whether ``payload`` reaches this socket within ``budget`` seconds."""
        deadline = asyncio.get_running_loop().time() + budget
        while payload not in self.sent:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return False
            self.arrived.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.arrived.wait(), timeout=min(remaining, 0.5))
        return True


class Replica:
    """One API process's share of the delivery path."""

    def __init__(self, gateway: RedisGateway) -> None:
        self.manager = ConnectionManager()
        self.bus = EventBus(gateway)
        self._fanout: asyncio.Task[None] | None = None

    async def watch(self, run_id: Any) -> RecordingSocket:
        """Register a socket for a run and start this replica's subscription."""
        socket = RecordingSocket()
        await self.manager.register(run_id, socket)  # type: ignore[arg-type]
        self._fanout = asyncio.create_task(run_fanout(self.manager, self.bus, run_id))
        return socket

    async def stop(self) -> None:
        if self._fanout is not None:
            self._fanout.cancel()
            await asyncio.gather(self._fanout, return_exceptions=True)


@pytest.fixture
def redis_url() -> str:
    url = os.environ.get("TEST_REDIS_URL")
    if not url:
        pytest.skip(SKIP_REASON)
    return url


@pytest.fixture
async def cluster(redis_url: str) -> AsyncIterator[tuple[Replica, Replica, EventBus]]:
    """Two replicas and a separate producer, each on its own connection."""
    settings = RedisSettings(url=redis_url)  # type: ignore[arg-type]
    gateways = [RedisGateway(create_redis(settings)) for _ in range(3)]
    replicas = (Replica(gateways[0]), Replica(gateways[1]))
    yield replicas[0], replicas[1], EventBus(gateways[2])
    for replica in replicas:
        await replica.stop()
    for gateway in gateways:
        await gateway.close()


async def _publish_until_seen(
    bus: EventBus, channel: str, payload: str, sockets: list[RecordingSocket]
) -> None:
    """Publish until every socket has the payload.

    SUBSCRIBE is not acknowledged and pub/sub has no replay, so one publish can lose a real
    race against the server registering a subscriber. Retrying removes that race rather
    than hiding it behind a sleep tuned to one machine's latency, and costs the test
    nothing: fan-out that is actually broken never delivers, however often we publish.
    """
    deadline = asyncio.get_running_loop().time() + RECEIVE_TIMEOUT
    while asyncio.get_running_loop().time() < deadline:
        assert await bus.publish(channel, payload) is True
        if all([await s.wait_for(payload, ATTEMPT_SECONDS) for s in sockets]):
            return
    pytest.fail(f"fan-out did not reach every replica within {RECEIVE_TIMEOUT}s")


class TestTwoReplicas:
    async def test_both_replicas_deliver_a_published_event(
        self, cluster: tuple[Replica, Replica, EventBus]
    ) -> None:
        """The criterion: publish, and a socket on each replica receives it."""
        first, second, producer = cluster
        run_id = new_run_id()
        sockets = [await first.watch(run_id), await second.watch(run_id)]

        await _publish_until_seen(producer, channel_for_run(run_id), '{"seq":1}', sockets)

        assert all(s.sent for s in sockets)
        assert {message for s in sockets for message in s.sent} == {'{"seq":1}'}

    @pytest.mark.security
    async def test_a_replica_ignores_another_run(
        self, cluster: tuple[Replica, Replica, EventBus]
    ) -> None:
        """Per-run channels are the isolation boundary for live delivery.

        Without it a socket would receive events from runs its owner cannot read — the
        replay endpoint's authorization would be intact and the socket would leak anyway.

        The watched run is used as a positive control: it proves fan-out was actually
        working during the window in which the unwatched run stayed silent. Without it this
        test would also pass if delivery were broken entirely.
        """
        first, _second, producer = cluster
        watched, unwatched = new_run_id(), new_run_id()
        socket = await first.watch(watched)

        # Confirm delivery works first. Publishing to the other run before the subscription
        # is registered would make the test pass for the wrong reason.
        await _publish_until_seen(producer, channel_for_run(watched), '{"seq":1}', [socket])

        await producer.publish(channel_for_run(unwatched), '{"leaked":true}')
        await asyncio.sleep(QUIET_SECONDS)

        assert socket.sent == ['{"seq":1}']
