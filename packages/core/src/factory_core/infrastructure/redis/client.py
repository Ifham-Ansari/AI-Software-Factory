"""Redis connection management.

Redis is a **latency optimisation and a coordination primitive, never the source of
truth**. Everything in this package is written so that Redis being unreachable degrades a
feature rather than failing a request:

* Events are already durable in Postgres before they are published (see
  ``events/publisher.py``); losing the publish costs liveness, not data.
* Rate limiting fails **open** — a limiter that cannot reach Redis must not lock every
  user out of the platform. The counter is an abuse control, not an authorization control.
* Locks fail **closed** — a lock that cannot be acquired must not be assumed held. The
  caller does not get to proceed.

Those two directions are opposite on purpose, and the difference is the blast radius of
being wrong: wrongly allowing an extra request is a nuisance, wrongly running two
deployments at once is an incident.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from redis.asyncio import Redis
from redis.exceptions import RedisError

from factory_core.config.integrations import RedisSettings
from factory_core.observability import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from types import TracebackType

logger = get_logger(__name__)


class RedisUnavailableError(Exception):
    """Redis could not be reached.

    Not an ``AppError``: it never reaches a client. Callers decide locally whether to
    degrade or fail, and translate to an application error only if the answer is "fail".
    """


def create_redis(settings: RedisSettings) -> Redis | None:
    """Build a Redis client, or ``None`` when none is configured.

    ``None`` rather than raising, because "no Redis" is a supported deployment: the
    platform runs with fan-out and rate limiting disabled, and every consumer here
    handles that.

    ``decode_responses=True`` because everything published is JSON text; the alternative
    is decoding at a dozen call sites.
    """
    if settings.url is None:
        return None
    # `from_url` is untyped in redis-py's stubs; the return is a Redis by contract.
    client: Redis = Redis.from_url(
        settings.url.get_secret_value(),
        max_connections=settings.max_connections,
        socket_timeout=settings.socket_timeout_seconds,
        socket_connect_timeout=settings.socket_timeout_seconds,
        decode_responses=True,
        health_check_interval=30,
    )
    return client


class RedisGateway:
    """A guarded handle to Redis that never raises at its call sites.

    Every consumer needs the same two behaviours — "is it there?" and "try this, and tell
    me if it did not work" — and implementing them per consumer produced the same
    try/except five times. Centralising it also gives one place that logs an outage,
    rather than five that log it on every operation.
    """

    def __init__(self, client: Redis | None) -> None:
        self._client = client
        self._degraded = False

    @property
    def is_available(self) -> bool:
        """Whether a client is configured at all."""
        return self._client is not None

    @property
    def client(self) -> Redis:
        """The underlying client.

        Raises:
            RedisUnavailableError: No Redis is configured. Callers that can degrade
                should check :attr:`is_available` first.
        """
        if self._client is None:
            msg = "Redis is not configured"
            raise RedisUnavailableError(msg)
        return self._client

    async def ping(self) -> bool:
        """Whether Redis answers right now. Never raises."""
        if self._client is None:
            return False
        try:
            await self._client.ping()
        except (RedisError, OSError):
            return False
        else:
            return True

    def note_outage(self, operation: str, error: Exception) -> None:
        """Record a Redis failure once per outage rather than once per operation.

        A Redis outage with traffic flowing produces thousands of identical lines a
        second, which buries the rest of the log at exactly the wrong moment.
        """
        if not self._degraded:
            self._degraded = True
            logger.warning("redis.degraded", operation=operation, error=type(error).__name__)

    def note_recovery(self) -> None:
        """Clear the outage flag after a successful operation."""
        if self._degraded:
            self._degraded = False
            logger.info("redis.recovered")

    async def close(self) -> None:
        """Release pooled connections."""
        if self._client is not None:
            await self._client.aclose()

    async def __aenter__(self) -> RedisGateway:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()
