"""Redis fan-out against a real broker [F-210, F-211].

Acceptance criterion: *an event published on one replica reaches sockets on another*.

These tests need a real Redis and skip without one, because what they verify is precisely
what a fake defines away. ``FakeRedis`` does not implement ``pubsub()`` at all — deliberately,
since a faked subscription would prove only that the fake forwards messages to itself, while
every bug this path has actually had lived in the connection: the TLS scheme, and a blocking
read cut short by the socket timeout.

``test_a_quiet_subscription_survives_the_socket_timeout`` is a regression guard for the
second of those. ``listen()`` issues an unbounded blocking read, which ``socket_timeout``
interrupts: a channel with nothing published raised ``TimeoutError`` after five seconds and
ended the subscription permanently. Runs are quiet most of the time, so live delivery died
on every socket shortly after it connected — and invisibly, because the socket stayed open
and clients kept recovering by replay.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from factory_core.config.integrations import RedisSettings
from factory_core.infrastructure.redis import EventBus, RedisGateway
from factory_core.infrastructure.redis.client import create_redis

pytestmark = pytest.mark.integration

SKIP_REASON = (
    "TEST_REDIS_URL is not set. These tests need a real Redis: they cover subscription "
    "behaviour (blocking reads, socket timeouts, cross-connection delivery) that the "
    "in-memory fake does not implement."
)

#: Long enough to outlast the 5s default ``socket_timeout`` that used to end a subscription.
IDLE_SECONDS = 7.0

#: How long to wait for one delivery attempt before publishing again.
ATTEMPT_SECONDS = 1.0

#: Overall budget for a payload to arrive. Generous because these run against whatever
#: Redis the environment provides, including a remote one across the internet.
RECEIVE_TIMEOUT = 30.0


@pytest.fixture
def redis_url() -> str:
    url = os.environ.get("TEST_REDIS_URL")
    if not url:
        pytest.skip(SKIP_REASON)
    return url


@pytest.fixture
def unique_channel() -> str:
    """A channel nobody else is using.

    Tests may run against a shared Redis, and pub/sub has no namespacing of its own, so a
    fixed channel name would let concurrent runs deliver each other's messages.
    """
    return f"factory:test:fanout:{uuid4().hex}"


@pytest.fixture
async def gateways(redis_url: str) -> AsyncIterator[list[RedisGateway]]:
    """Three independent connections: two subscribers and a producer.

    Separate gateways rather than one shared client is the point — it is what makes these
    distinct replicas rather than one process talking to itself.
    """
    settings = RedisSettings(url=redis_url)  # type: ignore[arg-type]
    built = [RedisGateway(create_redis(settings)) for _ in range(3)]
    yield built
    for gateway in built:
        await gateway.close()


class Collector:
    """Subscribes to a channel and records what arrives.

    ``seen`` is a set rather than a list because delivery here is deliberately retried —
    see :func:`_publish_until_seen` — so a payload may legitimately arrive more than once.
    Exactly-once is not a property Redis pub/sub has, and it is not what these tests are
    about; the durable ordering guarantee lives in Postgres and is tested against it.
    """

    def __init__(self) -> None:
        self.seen: set[str] = set()
        self.subscribed = asyncio.Event()
        self._arrived = asyncio.Event()

    async def run(self, bus: EventBus, channel: str) -> None:
        async with bus.subscribe(channel) as messages:
            self.subscribed.set()
            async for message in messages:
                self.seen.add(message)
                self._arrived.set()

    async def wait_for(self, payload: str, budget: float) -> bool:
        """Whether ``payload`` arrives within ``budget`` seconds.

        Named ``budget`` rather than ``timeout`` because this returns a verdict instead of
        raising, which is the opposite of what a ``timeout`` argument conventionally means.
        """
        deadline = asyncio.get_running_loop().time() + budget
        while payload not in self.seen:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return False
            self._arrived.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._arrived.wait(), timeout=min(remaining, 0.5))
        return True


async def _publish_until_seen(
    bus: EventBus, channel: str, payload: str, collectors: list[Collector]
) -> None:
    """Publish until every collector has the payload.

    SUBSCRIBE is not acknowledged by redis-py and pub/sub has no replay, so a single
    publish can lose a genuine race against the server registering a subscriber. Retrying
    removes that race instead of hiding it behind a sleep tuned to one machine's latency —
    and it keeps the test honest, because a subscription that is actually broken never
    confirms no matter how many times the payload is published.
    """
    deadline = asyncio.get_running_loop().time() + RECEIVE_TIMEOUT
    while asyncio.get_running_loop().time() < deadline:
        assert await bus.publish(channel, payload) is True
        outcomes = [await c.wait_for(payload, ATTEMPT_SECONDS) for c in collectors]
        if all(outcomes):
            return
    pytest.fail(f"payload was not delivered to every subscriber within {RECEIVE_TIMEOUT}s")


class TestCrossReplicaFanout:
    async def test_two_replicas_both_receive_a_published_event(
        self, gateways: list[RedisGateway], unique_channel: str
    ) -> None:
        """The acceptance criterion, on the real broker.

        Each subscriber holds its own connection, exactly as two API processes would. One
        payload must reach both.
        """
        first, second, producer = gateways
        collectors = [Collector(), Collector()]
        tasks = [
            asyncio.create_task(collectors[0].run(EventBus(first), unique_channel)),
            asyncio.create_task(collectors[1].run(EventBus(second), unique_channel)),
        ]
        try:
            await asyncio.gather(*(c.subscribed.wait() for c in collectors))

            await _publish_until_seen(EventBus(producer), unique_channel, '{"seq":1}', collectors)

            assert [c.seen for c in collectors] == [{'{"seq":1}'}, {'{"seq":1}'}]
        finally:
            await _cancel(tasks)

    @pytest.mark.failure
    async def test_a_quiet_subscription_survives_the_socket_timeout(
        self, gateways: list[RedisGateway], unique_channel: str
    ) -> None:
        """A run that emits nothing for a while must still deliver what comes next.

        The regression: the subscription used to die silently during the idle gap, so
        nothing published afterwards ever arrived and live updates were over for that
        socket. Retrying the publish does not weaken the test — a dead subscription
        confirms nothing however often the payload is sent.
        """
        subscriber, _unused, producer = gateways
        collector = Collector()
        task = asyncio.create_task(collector.run(EventBus(subscriber), unique_channel))
        try:
            await collector.subscribed.wait()
            bus = EventBus(producer)
            await _publish_until_seen(bus, unique_channel, '{"seq":1}', [collector])

            await asyncio.sleep(IDLE_SECONDS)

            await _publish_until_seen(bus, unique_channel, '{"seq":2}', [collector])
            assert collector.seen == {'{"seq":1}', '{"seq":2}'}
        finally:
            await _cancel([task])

    async def test_publishing_with_nobody_listening_is_not_an_error(
        self, gateways: list[RedisGateway], unique_channel: str
    ) -> None:
        """Fire-and-forget is the contract, not a defect.

        Durability belongs to Postgres; a publish nobody hears costs latency, and the
        client recovers the event by replaying. Asserted so the behaviour is a decision
        rather than an accident.
        """
        *_unused, producer = gateways

        assert await EventBus(producer).publish(unique_channel, '{"seq":1}') is True


class TestSubscriptionTeardown:
    @pytest.mark.failure
    async def test_cancelling_a_subscription_returns_its_connection(
        self, redis_url: str, unique_channel: str
    ) -> None:
        """Every socket that disconnects must give its connection back.

        Each subscription holds a dedicated pooled connection, and cancellation is the
        normal way one ends — the API cancels ``run_fanout`` when the last socket for a run
        goes away. A teardown that dropped the connection instead of returning it would
        exhaust the pool after ``max_connections`` disconnects, and every later socket
        would silently lose live delivery. The pool here is deliberately tiny so a leak
        shows up in a few cycles rather than ten.
        """
        settings = RedisSettings(url=redis_url, max_connections=2)  # type: ignore[arg-type]
        gateway = RedisGateway(create_redis(settings))
        bus = EventBus(gateway)
        pool = gateway.client.connection_pool

        try:
            for _ in range(4):
                collector = Collector()
                task = asyncio.create_task(collector.run(bus, unique_channel))
                await collector.subscribed.wait()
                await _cancel([task])

                assert len(pool._in_use_connections) == 0
        finally:
            await gateway.close()


async def _cancel(tasks: list[asyncio.Task[None]]) -> None:
    """Stop subscriber tasks and let their subscriptions tear down."""
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
