"""Redeeming an email verification code.

Bounded attempts and expiry are the core security properties of a six-digit code; both are
exercised here with a ``FrozenClock`` so they are exact rather than racing real seconds.
Issuing a code has its own suite — ``test_email_verification_issue.py``.
"""

from __future__ import annotations

import pytest

from factory_core.application.auth.verification import (
    CodeExhaustedError,
    CodeExpiredError,
    VerificationError,
)
from factory_core.config.email import VerificationSettings
from factory_core.domain.audit import AuditAction

from ._verification_harness import Harness

pytestmark = pytest.mark.unit


@pytest.fixture
def harness() -> Harness:
    return Harness()


class TestVerify:
    async def test_correct_code_verifies_the_user(self, harness: Harness) -> None:
        user = harness.make_user()
        await harness.service.issue(user, enforce_limits=False)
        code = harness.emails.last_code()

        verified = await harness.service.verify(user, code)

        assert verified.is_email_verified
        assert AuditAction.VERIFICATION_SUCCEEDED in harness.audit.actions()

    async def test_no_code_issued_yet(self, harness: Harness) -> None:
        user = harness.make_user()

        with pytest.raises(CodeExpiredError):
            await harness.service.verify(user, "123456")

    @pytest.mark.failure
    async def test_expired_code_rejected(self, harness: Harness) -> None:
        settings = VerificationSettings(ttl_seconds=60)
        harness = Harness(settings)
        user = harness.make_user()
        await harness.service.issue(user, enforce_limits=False)
        code = harness.emails.last_code()

        harness.clock.advance(61)

        with pytest.raises(CodeExpiredError):
            await harness.service.verify(user, code)

    @pytest.mark.failure
    async def test_wrong_code_decrements_remaining_attempts(self, harness: Harness) -> None:
        settings = VerificationSettings(max_attempts=3)
        harness = Harness(settings)
        user = harness.make_user()
        await harness.service.issue(user, enforce_limits=False)

        with pytest.raises(VerificationError, match="2 attempts remaining"):
            await harness.service.verify(user, "000000")

    @pytest.mark.security
    async def test_attempts_exhausted_destroys_the_code(self, harness: Harness) -> None:
        settings = VerificationSettings(max_attempts=2)
        harness = Harness(settings)
        user = harness.make_user()
        await harness.service.issue(user, enforce_limits=False)
        real_code = harness.emails.last_code()

        with pytest.raises(VerificationError):
            await harness.service.verify(user, "000000")
        with pytest.raises(CodeExhaustedError):
            await harness.service.verify(user, "000000")

        assert AuditAction.VERIFICATION_EXHAUSTED in harness.audit.actions()
        # The real code is dead too, even though it was never guessed.
        with pytest.raises(CodeExhaustedError):
            await harness.service.verify(user, real_code)

    async def test_consumed_code_cannot_be_reused(self, harness: Harness) -> None:
        user = harness.make_user()
        await harness.service.issue(user, enforce_limits=False)
        code = harness.emails.last_code()

        await harness.service.verify(user, code)

        with pytest.raises(CodeExpiredError):
            await harness.service.verify(user, code)

    async def test_verifying_twice_is_idempotent_on_the_timestamp(self, harness: Harness) -> None:
        """Re-verifying an already-verified account must not reset when it was proven."""
        user = harness.make_user()
        harness.users.verify(user.id)
        original = harness.users.users[user.id].email_verified_at

        result = await harness.users.mark_email_verified(user.id, now=harness.clock.now())

        assert result is not None
        assert result.email_verified_at == original
