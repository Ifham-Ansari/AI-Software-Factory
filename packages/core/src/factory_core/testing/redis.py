"""In-memory stand-ins for Redis, for deterministic tests.

Two doubles, because the tests need opposite things:

* :class:`FakeRedis` implements just enough of the client for the rate limiter, lock
  manager and idempotency store — including the two Lua scripts, evaluated natively.
  Time is injected, so TTL expiry is exact rather than a ``sleep``.
* :class:`BrokenRedis` raises :class:`RedisError` on every operation. That is what proves
  the acceptance criterion "with Redis stopped, jobs still run and events are still
  persisted": the code has to be exercised against a Redis that fails, not one that is
  merely absent, because those take different branches.
"""

from __future__ import annotations

from typing import Any

from redis.exceptions import RedisError


class FakeRedis:
    """A minimal in-memory Redis with controllable time."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._expiry: dict[str, float] = {}
        self.published: list[tuple[str, str]] = []
        self.now: float = 0.0

    def advance(self, seconds: float) -> None:
        """Move the clock, expiring anything whose TTL has passed."""
        self.now += seconds
        for key in [k for k, at in self._expiry.items() if at <= self.now]:
            self._values.pop(key, None)
            self._expiry.pop(key, None)

    def _live(self, key: str) -> bool:
        at = self._expiry.get(key)
        if at is not None and at <= self.now:
            self._values.pop(key, None)
            self._expiry.pop(key, None)
            return False
        return key in self._values

    async def ping(self) -> bool:
        """Always answers."""
        return True

    async def get(self, key: str) -> str | None:
        """Return a value, or ``None`` if absent or expired."""
        return self._values.get(key) if self._live(key) else None

    async def set(
        self,
        key: str,
        value: str,
        *,
        nx: bool = False,
        ex: int | None = None,
        px: int | None = None,
    ) -> bool | None:
        """Set a key, honouring ``NX`` and both TTL units."""
        if nx and self._live(key):
            return None
        self._values[key] = value
        if ex is not None:
            self._expiry[key] = self.now + ex
        elif px is not None:
            self._expiry[key] = self.now + px / 1000
        return True

    async def incr(self, key: str) -> int:
        """Increment a counter, treating an expired key as absent."""
        current = int(self._values[key]) if self._live(key) else 0
        current += 1
        self._values[key] = str(current)
        return current

    async def ttl(self, key: str) -> int:
        """Seconds remaining: -2 when absent, -1 when set without an expiry."""
        if not self._live(key):
            return -2
        at = self._expiry.get(key)
        return -1 if at is None else max(0, int(at - self.now))

    async def expire(self, key: str, seconds: int) -> bool:
        """Attach a TTL to an existing key."""
        if not self._live(key):
            return False
        self._expiry[key] = self.now + seconds
        return True

    async def delete(self, *keys: str) -> int:
        """Remove keys, returning how many existed."""
        removed = 0
        for key in keys:
            if self._values.pop(key, None) is not None:
                removed += 1
            self._expiry.pop(key, None)
        return removed

    async def publish(self, channel: str, message: str) -> int:
        """Record a publish. Returns 0 subscribers, as a real Redis would with none."""
        self.published.append((channel, message))
        return 0

    async def eval(self, script: str, _numkeys: int, key: str, *args: str) -> int:
        """Evaluate the two Lua scripts this codebase uses.

        Matching on the operation rather than parsing Lua: these are the only two
        scripts, and both are compare-and-act on a single key.
        """
        token = args[0] if args else ""
        held = await self.get(key)
        if held != token:
            return 0
        if "del" in script:
            await self.delete(key)
            return 1
        if "pexpire" in script:
            self._expiry[key] = self.now + int(args[1]) / 1000
            return 1
        return 0

    def pipeline(self) -> FakePipeline:
        """Return a pipeline that queues commands and runs them on execute."""
        return FakePipeline(self)

    async def aclose(self) -> None:
        """No-op: nothing to release."""

    def pubsub(self) -> Any:  # pragma: no cover - subscription is not faked
        msg = "FakeRedis does not implement pub/sub subscription"
        raise NotImplementedError(msg)


class FakePipeline:
    """Queues commands and applies them in order, like a real pipeline."""

    def __init__(self, client: FakeRedis) -> None:
        self._client = client
        self._queued: list[tuple[str, tuple[Any, ...]]] = []

    def incr(self, key: str) -> FakePipeline:
        """Queue an INCR."""
        self._queued.append(("incr", (key,)))
        return self

    def ttl(self, key: str) -> FakePipeline:
        """Queue a TTL."""
        self._queued.append(("ttl", (key,)))
        return self

    async def execute(self) -> list[Any]:
        """Run every queued command and return their results in order."""
        results: list[Any] = []
        for name, args in self._queued:
            results.append(await getattr(self._client, name)(*args))
        self._queued.clear()
        return results


class BrokenRedis:
    """A Redis that fails every operation.

    Used to prove degradation paths: the rate limiter must fail open, the lock manager
    must fail closed, and the event publisher must leave events durable regardless.
    """

    def __init__(self) -> None:
        self.attempts = 0

    def _fail(self) -> RedisError:
        self.attempts += 1
        return RedisError("connection refused")

    async def ping(self) -> bool:
        """Report unreachable rather than raising, matching the gateway's contract."""
        raise self._fail()

    async def get(self, *_args: Any, **_kwargs: Any) -> str | None:
        raise self._fail()

    async def set(self, *_args: Any, **_kwargs: Any) -> bool | None:
        raise self._fail()

    async def incr(self, *_args: Any, **_kwargs: Any) -> int:
        raise self._fail()

    async def expire(self, *_args: Any, **_kwargs: Any) -> bool:
        raise self._fail()

    async def delete(self, *_args: Any, **_kwargs: Any) -> int:
        raise self._fail()

    async def publish(self, *_args: Any, **_kwargs: Any) -> int:
        raise self._fail()

    async def eval(self, *_args: Any, **_kwargs: Any) -> int:
        raise self._fail()

    def pipeline(self) -> Any:
        """Return a pipeline whose execute fails."""
        return _BrokenPipeline(self)

    async def aclose(self) -> None:
        """No-op."""

    def pubsub(self) -> Any:
        raise self._fail()


class _BrokenPipeline:
    """A pipeline that accepts commands and fails on execute."""

    def __init__(self, client: BrokenRedis) -> None:
        self._client = client

    def incr(self, _key: str) -> _BrokenPipeline:
        return self

    def ttl(self, _key: str) -> _BrokenPipeline:
        return self

    async def execute(self) -> list[Any]:
        raise self._client._fail()
