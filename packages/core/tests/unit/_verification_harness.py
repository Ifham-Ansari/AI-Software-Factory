"""Shared test harness for the email verification unit suite.

Split out of what used to be one 250+ line test module so ``test_email_verification_issue.py``
(issuing and rate limits) and ``test_email_verification_verify.py`` (redeeming a code) can
each stay a single, focused file while sharing the same fixtures.
"""

from __future__ import annotations

from datetime import UTC, datetime

from factory_core.application.auth.verification import EmailVerificationService
from factory_core.application.ports import FrozenClock
from factory_core.config.email import VerificationSettings
from factory_core.domain.entities import User, UserStatus
from factory_core.domain.ids import new_user_id
from factory_core.testing import (
    FakeAuditRepository,
    FakeUserRepository,
    FakeVerificationRepository,
    RecordingEmailSender,
)

EMAIL = "ada@example.com"


class Harness:
    """Everything an ``EmailVerificationService`` needs."""

    def __init__(self, settings: VerificationSettings | None = None) -> None:
        self.users = FakeUserRepository()
        self.verifications = FakeVerificationRepository()
        self.audit = FakeAuditRepository()
        self.emails = RecordingEmailSender()
        self.clock = FrozenClock(datetime(2026, 1, 15, 12, 0, tzinfo=UTC))
        self.settings = settings or VerificationSettings()
        self.service = EmailVerificationService(
            users=self.users,  # type: ignore[arg-type]
            verifications=self.verifications,  # type: ignore[arg-type]
            audit=self.audit,  # type: ignore[arg-type]
            sender=self.emails,
            settings=self.settings,
            clock=self.clock,
            request_id="test-request",
        )

    def make_user(self, email: str = EMAIL) -> User:
        now = self.clock.now()
        user = User(
            id=new_user_id(),
            email=email,
            display_name="Ada Lovelace",
            status=UserStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        self.users.users[user.id] = user
        self.users.hashes[user.id] = "$argon2id$fake"
        return user
