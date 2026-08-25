"""Redis-backed coordination: fan-out, rate limiting, idempotency, locks."""

from factory_core.infrastructure.redis.client import (
    RedisGateway,
    RedisUnavailableError,
    create_redis,
)
from factory_core.infrastructure.redis.idempotency import (
    IdempotencyRecord,
    IdempotencyState,
    IdempotencyStore,
)
from factory_core.infrastructure.redis.locks import Lock, LockManager, LockNotAcquiredError
from factory_core.infrastructure.redis.pubsub import EventBus
from factory_core.infrastructure.redis.rate_limit import (
    RateLimit,
    RateLimitedError,
    RateLimiter,
    RateLimitResult,
    RateLimitScope,
)

__all__ = [
    "EventBus",
    "IdempotencyRecord",
    "IdempotencyState",
    "IdempotencyStore",
    "Lock",
    "LockManager",
    "LockNotAcquiredError",
    "RateLimit",
    "RateLimitResult",
    "RateLimitScope",
    "RateLimitedError",
    "RateLimiter",
    "RedisGateway",
    "RedisUnavailableError",
    "create_redis",
]
