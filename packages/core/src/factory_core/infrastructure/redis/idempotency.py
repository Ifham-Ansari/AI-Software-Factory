"""Idempotency records.

Some operations cost money or have external side effects — provisioning a database,
calling a deployment provider. Doing one twice because a retry arrived is expensive and,
for a provisioning call, not automatically reversible.

The store gives a two-phase claim:

1. :meth:`IdempotencyStore.begin` claims a key with ``SET NX``. Exactly one caller wins.
2. The winner does the work and calls :meth:`complete` with a small result.
3. Anyone arriving later gets :class:`IdempotencyRecord` back and skips the work.

The window between claim and completion is represented explicitly as ``IN_PROGRESS``, so
a concurrent caller can tell "someone is doing this right now" from "this was already
done" — those need different handling, and collapsing them causes either a duplicate call
or a lost result.

Records expire (24h by default, per architecture.md §10.3). Idempotency is a
short-horizon deduplication window, not a permanent ledger; the permanent record of what
happened lives in Postgres.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from redis.exceptions import RedisError

from factory_core.infrastructure.redis.client import RedisGateway
from factory_core.observability import get_logger

logger = get_logger(__name__)

#: How long a completed record is remembered.
DEFAULT_TTL_SECONDS = 86_400

#: How long a claim may stay in progress before it is considered abandoned. Shorter than
#: the completed TTL so a crashed caller does not block a retry for a whole day.
DEFAULT_CLAIM_TTL_SECONDS = 900


class IdempotencyState(StrEnum):
    """Where a keyed operation has got to."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    """What is known about a previously seen key."""

    state: IdempotencyState
    result: dict[str, Any] | None = None

    @property
    def is_completed(self) -> bool:
        """Whether the work finished and its result is available."""
        return self.state is IdempotencyState.COMPLETED


class IdempotencyStore:
    """Claims and completes idempotency keys."""

    def __init__(self, gateway: RedisGateway) -> None:
        self._gateway = gateway

    async def begin(
        self, key: str, *, claim_ttl_seconds: int = DEFAULT_CLAIM_TTL_SECONDS
    ) -> IdempotencyRecord | None:
        """Claim a key for this caller.

        Returns:
            ``None`` when the claim was won and the caller should do the work. An
            :class:`IdempotencyRecord` when someone else already claimed or completed it.

        With Redis unavailable this returns ``None`` — deduplication is unavailable, so
        the operation proceeds. The alternative, refusing to act, would mean a Redis
        outage blocks all provisioning; the durable guards against duplicate side effects
        live in Postgres (``jobs.idempotency_key``).
        """
        if not self._gateway.is_available:
            return None
        redis_key = self._key(key)
        payload = json.dumps({"state": IdempotencyState.IN_PROGRESS.value})
        try:
            claimed = await self._gateway.client.set(
                redis_key, payload, nx=True, ex=claim_ttl_seconds
            )
            if claimed:
                self._gateway.note_recovery()
                return None
            existing = await self._gateway.client.get(redis_key)
        except (RedisError, OSError) as exc:
            self._gateway.note_outage("idempotency_begin", exc)
            return None

        self._gateway.note_recovery()
        return _decode(existing)

    async def complete(
        self,
        key: str,
        result: dict[str, Any] | None = None,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        """Record a key as completed, with an optional small result."""
        if not self._gateway.is_available:
            return
        payload = json.dumps({"state": IdempotencyState.COMPLETED.value, "result": result or {}})
        try:
            await self._gateway.client.set(self._key(key), payload, ex=ttl_seconds)
        except (RedisError, OSError) as exc:
            self._gateway.note_outage("idempotency_complete", exc)

    async def get(self, key: str) -> IdempotencyRecord | None:
        """Look up a key without claiming it."""
        if not self._gateway.is_available:
            return None
        try:
            raw = await self._gateway.client.get(self._key(key))
        except (RedisError, OSError) as exc:
            self._gateway.note_outage("idempotency_get", exc)
            return None
        return _decode(raw)

    async def release(self, key: str) -> None:
        """Drop a claim so the work can be retried immediately.

        Called when the claimed work *failed*. Leaving the claim in place would make the
        caller wait out the claim TTL before being allowed to try again.
        """
        if not self._gateway.is_available:
            return
        try:
            await self._gateway.client.delete(self._key(key))
        except (RedisError, OSError) as exc:
            self._gateway.note_outage("idempotency_release", exc)

    @staticmethod
    def _key(key: str) -> str:
        return f"idem:{key}"


def _decode(raw: str | None) -> IdempotencyRecord | None:
    """Parse a stored record, tolerating one written by an older revision."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
        state = IdempotencyState(data["state"])
    except (ValueError, KeyError, TypeError):
        # An unreadable record must not wedge the caller forever. Treating it as absent
        # means the work runs again, which idempotent handlers tolerate by definition.
        return None
    result = data.get("result")
    return IdempotencyRecord(state=state, result=result if isinstance(result, dict) else None)
