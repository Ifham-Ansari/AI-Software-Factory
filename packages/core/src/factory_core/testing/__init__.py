"""Test support shipped with the package.

Lives in the distributed package, not in a test directory, so ``packages/core`` and
``apps/api`` share one implementation of each fake. Duplicated fakes drift, and a drifted
fake tests itself rather than the system.

Nothing here is imported by production code paths.
"""

from factory_core.testing.identity import (
    FakeAuditRepository,
    FakeRefreshTokenRepository,
    FakeUserRepository,
)
from factory_core.testing.projects import FakeProjectRepository, FakeProjectStore
from factory_core.testing.redis import BrokenRedis, FakeRedis
from factory_core.testing.verification import (
    FakeVerificationRepository,
    RecordingEmailSender,
)

__all__ = [
    "BrokenRedis",
    "FakeAuditRepository",
    "FakeProjectRepository",
    "FakeProjectStore",
    "FakeRedis",
    "FakeRefreshTokenRepository",
    "FakeUserRepository",
    "FakeVerificationRepository",
    "RecordingEmailSender",
]
