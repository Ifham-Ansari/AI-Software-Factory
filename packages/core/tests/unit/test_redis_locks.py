"""Distributed locks and idempotency records [F-207].

Split from ``test_redis_primitives.py`` (rate limiting) because the degradation directions
are opposite and worth reading side by side with the code rather than with each other:
the **lock fails closed**, while the limiter fails open. Assuming a lock is held when it
cannot be verified is how two concurrent deployments happen.
"""

from __future__ import annotations

import pytest

from factory_core.infrastructure.redis import (
    IdempotencyState,
    IdempotencyStore,
    LockManager,
    LockNotAcquiredError,
    RateLimit,
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


class TestLocks:
    async def test_acquire_and_release(self, gateway: RedisGateway) -> None:
        manager = LockManager(gateway)

        lock = await manager.acquire("project:1:deploy")

        assert lock is not None
        assert await lock.release()

    async def test_a_held_lock_blocks_a_second_holder(self, gateway: RedisGateway) -> None:
        manager = LockManager(gateway)
        await manager.acquire("project:1:deploy")

        assert await manager.acquire("project:1:deploy") is None

    async def test_a_released_lock_can_be_retaken(self, gateway: RedisGateway) -> None:
        manager = LockManager(gateway)
        first = await manager.acquire("project:1:deploy")
        assert first is not None
        await first.release()

        assert await manager.acquire("project:1:deploy") is not None

    async def test_an_expired_lease_frees_the_lock(
        self, gateway: RedisGateway, fake: FakeRedis
    ) -> None:
        """A holder that dies must not block the resource forever."""
        manager = LockManager(gateway)
        await manager.acquire("project:1:deploy", ttl_seconds=10)

        fake.advance(11)

        assert await manager.acquire("project:1:deploy") is not None

    @pytest.mark.security
    async def test_releasing_someone_elses_lock_does_nothing(
        self, gateway: RedisGateway, fake: FakeRedis
    ) -> None:
        """The classic bug: your lease expired, someone else acquired, and your DEL
        releases *their* lock. Compare-and-delete prevents it."""
        manager = LockManager(gateway)
        mine = await manager.acquire("shared", ttl_seconds=10)
        assert mine is not None
        fake.advance(11)
        theirs = await manager.acquire("shared", ttl_seconds=60)
        assert theirs is not None

        assert not await mine.release()
        # Theirs is untouched.
        assert await manager.acquire("shared") is None

    async def test_renewal_extends_the_lease(self, gateway: RedisGateway, fake: FakeRedis) -> None:
        manager = LockManager(gateway)
        lock = await manager.acquire("slow-task", ttl_seconds=10)
        assert lock is not None

        fake.advance(8)
        assert await lock.renew(60)
        fake.advance(8)

        assert await manager.acquire("slow-task") is None

    async def test_guard_releases_on_exit(self, gateway: RedisGateway) -> None:
        manager = LockManager(gateway)

        async with manager.guard("guarded"):
            assert await manager.acquire("guarded") is None

        assert await manager.acquire("guarded") is not None

    @pytest.mark.failure
    async def test_guard_releases_even_when_the_body_raises(self, gateway: RedisGateway) -> None:
        manager = LockManager(gateway)

        with pytest.raises(RuntimeError):
            async with manager.guard("guarded"):
                raise RuntimeError

        assert await manager.acquire("guarded") is not None


@pytest.mark.failure
class TestLockDegradation:
    async def test_fails_closed_when_redis_errors(self) -> None:
        """The opposite of the rate limiter, deliberately."""
        manager = LockManager(RedisGateway(BrokenRedis()))  # type: ignore[arg-type]

        assert await manager.acquire("project:1:deploy") is None

    async def test_guard_refuses_when_the_lock_cannot_be_taken(self) -> None:
        manager = LockManager(RedisGateway(BrokenRedis()))  # type: ignore[arg-type]

        with pytest.raises(LockNotAcquiredError):
            async with manager.guard("project:1:deploy"):
                pytest.fail("the guarded body must not run")


class TestIdempotency:
    async def test_first_caller_wins_the_claim(self, gateway: RedisGateway) -> None:
        store = IdempotencyStore(gateway)

        assert await store.begin("provision:1") is None

    async def test_second_caller_sees_work_in_progress(self, gateway: RedisGateway) -> None:
        """Distinguishable from "already done", because they need different handling."""
        store = IdempotencyStore(gateway)
        await store.begin("provision:1")

        record = await store.begin("provision:1")

        assert record is not None
        assert record.state is IdempotencyState.IN_PROGRESS
        assert not record.is_completed

    async def test_completion_publishes_the_result(self, gateway: RedisGateway) -> None:
        store = IdempotencyStore(gateway)
        await store.begin("provision:1")
        await store.complete("provision:1", {"database_id": "db-42"})

        record = await store.begin("provision:1")

        assert record is not None
        assert record.is_completed
        assert record.result == {"database_id": "db-42"}

    async def test_release_allows_an_immediate_retry(self, gateway: RedisGateway) -> None:
        """Called when the claimed work failed; without it the caller waits out the TTL."""
        store = IdempotencyStore(gateway)
        await store.begin("provision:1")

        await store.release("provision:1")

        assert await store.begin("provision:1") is None

    async def test_keys_are_independent(self, gateway: RedisGateway) -> None:
        store = IdempotencyStore(gateway)
        await store.begin("provision:1")

        assert await store.begin("provision:2") is None

    @pytest.mark.failure
    async def test_unreadable_record_does_not_wedge_the_caller(
        self, gateway: RedisGateway, fake: FakeRedis
    ) -> None:
        """A record written by an older revision must not block forever."""
        await fake.set("idem:provision:1", "not json")

        assert await IdempotencyStore(gateway).get("provision:1") is None

    @pytest.mark.failure
    async def test_degrades_to_no_deduplication(self) -> None:
        """With Redis down the operation proceeds; the durable guard is jobs.idempotency_key."""
        store = IdempotencyStore(RedisGateway(BrokenRedis()))  # type: ignore[arg-type]

        assert await store.begin("provision:1") is None
        await store.complete("provision:1", {"ok": True})
