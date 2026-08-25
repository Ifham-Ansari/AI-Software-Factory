"""Rate limiting [F-207].

The degradation test is the important one. The limiter **fails open**: if Redis is
unreachable the request is allowed. That is deliberate and it is the opposite of how the
lock behaves — a limiter that failed closed would convert a Redis outage into a total
platform outage. Locks and idempotency are in ``test_redis_locks.py``.
"""

from __future__ import annotations

import pytest

from factory_core.infrastructure.redis import (
    RateLimit,
    RateLimitedError,
    RateLimiter,
    RateLimitScope,
    RedisGateway,
)
from factory_core.testing import BrokenRedis, FakeRedis

pytestmark = pytest.mark.unit

LIMIT = RateLimit(max_requests=3, window_seconds=60)


@pytest.fixture
def fake() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def gateway(fake: FakeRedis) -> RedisGateway:
    return RedisGateway(fake)  # type: ignore[arg-type]


class TestRateLimiter:
    async def test_requests_under_the_limit_are_allowed(self, gateway: RedisGateway) -> None:
        limiter = RateLimiter(gateway)

        results = [await limiter.check(RateLimitScope.USER, "u1", LIMIT) for _ in range(3)]

        assert all(r.allowed for r in results)
        assert [r.remaining for r in results] == [2, 1, 0]

    @pytest.mark.failure
    async def test_exceeding_the_limit_is_refused_with_retry_after(
        self, gateway: RedisGateway
    ) -> None:
        """The acceptance criterion: 429 with Retry-After."""
        limiter = RateLimiter(gateway)
        for _ in range(3):
            await limiter.check(RateLimitScope.USER, "u1", LIMIT)

        result = await limiter.check(RateLimitScope.USER, "u1", LIMIT)

        assert result.limited
        assert result.retry_after > 0

    @pytest.mark.failure
    async def test_enforce_raises_with_retry_after(self, gateway: RedisGateway) -> None:
        limiter = RateLimiter(gateway)
        for _ in range(3):
            await limiter.enforce(RateLimitScope.IP, "1.2.3.4", LIMIT)

        with pytest.raises(RateLimitedError) as exc_info:
            await limiter.enforce(RateLimitScope.IP, "1.2.3.4", LIMIT)

        assert exc_info.value.status_code == 429
        assert exc_info.value.retry_after > 0
        assert exc_info.value.details["retry_after"] > 0

    async def test_the_window_resets(self, gateway: RedisGateway, fake: FakeRedis) -> None:
        limiter = RateLimiter(gateway)
        for _ in range(3):
            await limiter.check(RateLimitScope.USER, "u1", LIMIT)

        fake.advance(61)

        assert (await limiter.check(RateLimitScope.USER, "u1", LIMIT)).allowed

    async def test_scopes_and_identifiers_are_independent(self, gateway: RedisGateway) -> None:
        """One user exhausting their limit must not affect anyone else."""
        limiter = RateLimiter(gateway)
        for _ in range(3):
            await limiter.check(RateLimitScope.USER, "noisy", LIMIT)

        assert (await limiter.check(RateLimitScope.USER, "quiet", LIMIT)).allowed
        assert (await limiter.check(RateLimitScope.IP, "noisy", LIMIT)).allowed

    @pytest.mark.failure
    async def test_a_counter_without_a_ttl_is_repaired(
        self, gateway: RedisGateway, fake: FakeRedis
    ) -> None:
        """If a process died between INCR and EXPIRE the key would never reset, banning
        the caller forever. The limiter re-applies the TTL instead."""
        await fake.set("rl:user:u1", "1")

        result = await RateLimiter(gateway).check(RateLimitScope.USER, "u1", LIMIT)

        assert result.allowed
        assert await fake.ttl("rl:user:u1") > 0


@pytest.mark.failure
class TestRateLimiterDegradation:
    async def test_fails_open_when_redis_errors(self) -> None:
        """A limiter that failed closed would lock every user out during an outage."""
        broken = BrokenRedis()
        limiter = RateLimiter(RedisGateway(broken))  # type: ignore[arg-type]

        for _ in range(10):
            assert (await limiter.check(RateLimitScope.USER, "u1", LIMIT)).allowed

        assert broken.attempts > 0, "the limiter did not actually try Redis"

    async def test_fails_open_when_redis_is_absent(self) -> None:
        limiter = RateLimiter(RedisGateway(None))

        assert (await limiter.check(RateLimitScope.USER, "u1", LIMIT)).allowed
