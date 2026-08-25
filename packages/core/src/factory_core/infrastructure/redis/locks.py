"""Distributed locks.

One deploy per project at a time, one migration per environment at a time. The lock is a
Redis key holding a random token, set with ``NX`` and an expiry.

**This lock fails closed**, unlike the rate limiter. If Redis is unreachable, acquisition
fails and the caller does not proceed. Assuming a lock is held when it cannot be verified
is how two concurrent deployments happen.

Two details that are easy to get wrong and are handled here:

* **Release is compare-and-delete, via Lua.** Deleting a key you do not own is the classic
  bug: your lease expired, someone else acquired, and your ``DEL`` releases *their* lock.
  The script checks the token and deletes atomically.
* **The lease is finite and renewable.** A holder that dies must not block the resource
  forever, so every lock has a TTL; a holder doing legitimate long work calls
  :meth:`Lock.renew` rather than taking a lock long enough to cover the worst case.

This is single-instance Redis locking. It is sufficient here — Upstash is a single logical
endpoint and the protected operations are already idempotent — and it is not Redlock.
"""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast

from redis.exceptions import RedisError

from factory_core.infrastructure.redis.client import RedisGateway
from factory_core.observability import get_logger

logger = get_logger(__name__)

#: Compare-and-delete. Releasing a lock you no longer hold would release someone else's.
_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""

#: Compare-and-extend, for the same reason.
_RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('pexpire', KEYS[1], ARGV[2])
else
    return 0
end
"""


async def _run_script(gateway: RedisGateway, script: str, key: str, *args: str) -> object:
    """Run a Lua script against one key.

    Wrapped because redis-py types ``eval`` as returning ``Awaitable[str] | str``, which
    is not directly awaitable as far as the type checker is concerned. The cast is
    confined here rather than repeated at each call site.
    """
    return await cast("Any", gateway.client.eval(script, 1, key, *args))


class LockNotAcquiredError(Exception):
    """The lock is held by someone else, or Redis could not be reached."""


@dataclass(slots=True)
class Lock:
    """A held lock, and the token proving this holder owns it."""

    key: str
    token: str
    _manager: LockManager

    async def release(self) -> bool:
        """Release the lock if still owned. Returns whether anything was released."""
        return await self._manager.release(self.key, self.token)

    async def renew(self, ttl_seconds: float) -> bool:
        """Extend the lease. Returns ``False`` if ownership was already lost."""
        return await self._manager.renew(self.key, self.token, ttl_seconds)


class LockManager:
    """Acquires and releases distributed locks."""

    def __init__(self, gateway: RedisGateway) -> None:
        self._gateway = gateway

    async def acquire(self, resource: str, *, ttl_seconds: float = 60.0) -> Lock | None:
        """Try once to acquire a lock.

        Returns:
            The held lock, or ``None`` if it is held elsewhere or Redis is unreachable.
            Both are "you may not proceed", which is why they share a return value.
        """
        if not self._gateway.is_available:
            return None
        key = f"lock:{resource}"
        token = secrets.token_urlsafe(24)
        try:
            acquired = await self._gateway.client.set(
                key, token, nx=True, px=int(ttl_seconds * 1000)
            )
        except (RedisError, OSError) as exc:
            self._gateway.note_outage("lock_acquire", exc)
            return None
        self._gateway.note_recovery()
        if not acquired:
            return None
        return Lock(key=key, token=token, _manager=self)

    async def release(self, key: str, token: str) -> bool:
        """Release a lock, only if this token still owns it."""
        if not self._gateway.is_available:
            return False
        try:
            released = await _run_script(self._gateway, _RELEASE_SCRIPT, key, token)
        except (RedisError, OSError) as exc:
            self._gateway.note_outage("lock_release", exc)
            return False
        return bool(released)

    async def renew(self, key: str, token: str, ttl_seconds: float) -> bool:
        """Extend a lease, only if this token still owns it."""
        if not self._gateway.is_available:
            return False
        try:
            renewed = await _run_script(
                self._gateway, _RENEW_SCRIPT, key, token, str(int(ttl_seconds * 1000))
            )
        except (RedisError, OSError) as exc:
            self._gateway.note_outage("lock_renew", exc)
            return False
        return bool(renewed)

    @asynccontextmanager
    async def guard(self, resource: str, *, ttl_seconds: float = 60.0) -> AsyncIterator[Lock]:
        """Hold a lock for the duration of a block.

        Raises:
            LockNotAcquiredError: The lock could not be taken. Failing closed: a caller
                that cannot get the lock must not run the protected work.
        """
        lock = await self.acquire(resource, ttl_seconds=ttl_seconds)
        if lock is None:
            msg = f"could not acquire lock for {resource}"
            raise LockNotAcquiredError(msg)
        try:
            yield lock
        finally:
            await lock.release()
