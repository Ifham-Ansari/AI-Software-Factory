"""Rate limiting.

A fixed-window counter: ``INCR`` a key, set its TTL on first use, refuse once the count
exceeds the limit. Fixed windows allow a burst of up to 2x the limit across a boundary,
which is a known and accepted trade — a sliding-window log costs a sorted set and a
trim on every request to smooth a burst that is not, at our volumes, the thing that hurts.

**This limiter fails open.** If Redis is unreachable the request is allowed. That is
deliberate and it is the opposite of how the lock behaves: rate limiting is an abuse
control, and a limiter that fails closed converts a Redis outage into a total platform
outage. Abuse during a Redis outage is a smaller problem than everyone being locked out.

The counter is never used for authorization — only for throttling.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from redis.exceptions import RedisError

from factory_core.errors import AppError, ErrorCode
from factory_core.infrastructure.redis.client import RedisGateway


class RateLimitScope(StrEnum):
    """What a limit is counted against."""

    USER = "user"
    IP = "ip"
    PROJECT = "project"


class RateLimitedError(AppError):
    """The caller exceeded a rate limit.

    Carries ``retry_after`` in ``details`` so the API layer can set the ``Retry-After``
    header without re-deriving it.
    """

    code = ErrorCode.RATE_LIMITED
    status_code = 429
    message = "Too many requests. Please slow down."

    def __init__(self, retry_after: int, message: str | None = None) -> None:
        super().__init__(message, details={"retry_after": retry_after})
        self.retry_after = retry_after


@dataclass(frozen=True, slots=True)
class RateLimit:
    """A limit of ``max_requests`` per ``window_seconds``."""

    max_requests: int
    window_seconds: int

    def __post_init__(self) -> None:
        if self.max_requests < 1 or self.window_seconds < 1:
            msg = "rate limit requires max_requests >= 1 and window_seconds >= 1"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    """The outcome of one limit check."""

    allowed: bool
    remaining: int
    retry_after: int

    @property
    def limited(self) -> bool:
        """Whether this request should be refused."""
        return not self.allowed


class RateLimiter:
    """Fixed-window rate limiting backed by Redis."""

    def __init__(self, gateway: RedisGateway) -> None:
        self._gateway = gateway

    async def check(
        self, scope: RateLimitScope, identifier: str, limit: RateLimit
    ) -> RateLimitResult:
        """Count one request against a limit and report whether it is allowed.

        Never raises for infrastructure reasons — an unreachable Redis returns an
        allowing result. See the module docstring for why.
        """
        if not self._gateway.is_available:
            return RateLimitResult(allowed=True, remaining=limit.max_requests, retry_after=0)

        key = f"rl:{scope.value}:{identifier}"
        try:
            pipeline = self._gateway.client.pipeline()
            pipeline.incr(key)
            pipeline.ttl(key)
            count, ttl = await pipeline.execute()

            # TTL of -1 means the key exists without an expiry, which happens if the
            # process died between INCR and EXPIRE. Setting it here repairs that rather
            # than leaving a counter that never resets and bans the caller forever.
            if ttl is None or ttl < 0:
                await self._gateway.client.expire(key, limit.window_seconds)
                ttl = limit.window_seconds
        except (RedisError, OSError) as exc:
            self._gateway.note_outage("rate_limit", exc)
            return RateLimitResult(allowed=True, remaining=limit.max_requests, retry_after=0)

        self._gateway.note_recovery()
        used = int(count)
        remaining = max(0, limit.max_requests - used)
        if used > limit.max_requests:
            return RateLimitResult(allowed=False, remaining=0, retry_after=max(1, int(ttl)))
        return RateLimitResult(allowed=True, remaining=remaining, retry_after=0)

    async def enforce(
        self, scope: RateLimitScope, identifier: str, limit: RateLimit
    ) -> RateLimitResult:
        """Check a limit and raise when it is exceeded.

        Raises:
            RateLimitedError: The limit is exhausted.
        """
        result = await self.check(scope, identifier, limit)
        if result.limited:
            raise RateLimitedError(result.retry_after)
        return result

    async def reset(self, scope: RateLimitScope, identifier: str) -> None:
        """Clear a counter. Used by tests and by operator tooling."""
        if not self._gateway.is_available:
            return
        try:
            await self._gateway.client.delete(f"rl:{scope.value}:{identifier}")
        except (RedisError, OSError) as exc:
            self._gateway.note_outage("rate_limit_reset", exc)
