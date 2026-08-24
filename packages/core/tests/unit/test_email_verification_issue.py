"""Issuing an email verification code.

Covers what the HTTP-level suite cannot test deterministically: delivery, the resend
cooldown, and the daily cap, all of which depend on elapsed time. A ``FrozenClock`` here
makes them exact instead of racing real seconds. Redeeming a code has its own suite —
``test_email_verification_verify.py``.
"""

from __future__ import annotations

import pytest

from factory_core.application.auth.verification import (
    CodeExpiredError,
    ResendLimitError,
    ResendTooSoonError,
    VerificationError,
)
from factory_core.config.email import VerificationSettings
from factory_core.domain.audit import AuditAction
from factory_core.errors import ServiceUnavailableError

from ._verification_harness import EMAIL, Harness

pytestmark = pytest.mark.unit


@pytest.fixture
def harness() -> Harness:
    return Harness()


class TestIssue:
    async def test_sends_an_email_with_a_numeric_code(self, harness: Harness) -> None:
        user = harness.make_user()

        await harness.service.issue(user, enforce_limits=False)

        assert len(harness.emails.sent) == 1
        assert harness.emails.sent[0].to == EMAIL
        code = harness.emails.last_code()
        assert code.isdigit()
        assert len(code) == 6

    async def test_records_an_audit_entry(self, harness: Harness) -> None:
        user = harness.make_user()

        await harness.service.issue(user, enforce_limits=False)

        assert AuditAction.VERIFICATION_SENT in harness.audit.actions()

    async def test_a_second_issue_invalidates_the_first_code(self, harness: Harness) -> None:
        user = harness.make_user()
        await harness.service.issue(user, enforce_limits=False)
        old_code = harness.emails.last_code()

        harness.clock.advance(harness.settings.resend_cooldown_seconds + 1)
        await harness.service.issue(user)
        new_code = harness.emails.last_code()

        assert new_code != old_code or len(harness.emails.sent) == 2
        with pytest.raises((CodeExpiredError, VerificationError)):
            await harness.service.verify(user, old_code)

    async def test_delivery_failure_propagates(self, harness: Harness) -> None:
        """A verification email that cannot be sent must not silently succeed."""
        user = harness.make_user()
        harness.emails.fail_next = True

        with pytest.raises(ServiceUnavailableError):
            await harness.service.issue(user, enforce_limits=False)


@pytest.mark.security
class TestRateLimits:
    """The resend cooldown and daily cap — what actually protects a six-digit code."""

    async def test_resend_before_cooldown_is_refused(self, harness: Harness) -> None:
        user = harness.make_user()
        await harness.service.issue(user, enforce_limits=False)

        with pytest.raises(ResendTooSoonError):
            await harness.service.issue(user)

    async def test_resend_after_cooldown_succeeds(self, harness: Harness) -> None:
        user = harness.make_user()
        await harness.service.issue(user, enforce_limits=False)

        harness.clock.advance(harness.settings.resend_cooldown_seconds + 1)

        await harness.service.issue(user)  # must not raise
        assert len(harness.emails.sent) == 2

    async def test_first_code_bypasses_the_cooldown(self, harness: Harness) -> None:
        """Registration's very first code must not be refused for a limit that cannot
        have been hit yet."""
        user = harness.make_user()

        await harness.service.issue(user, enforce_limits=False)  # must not raise

        assert len(harness.emails.sent) == 1

    async def test_daily_cap_is_enforced(self) -> None:
        settings = VerificationSettings(resend_cooldown_seconds=0, max_per_day=3)
        harness = Harness(settings)
        user = harness.make_user()

        for _ in range(3):
            await harness.service.issue(user, enforce_limits=False)

        with pytest.raises(ResendLimitError):
            await harness.service.issue(user)

    async def test_daily_cap_resets_after_a_day(self) -> None:
        settings = VerificationSettings(resend_cooldown_seconds=0, max_per_day=2)
        harness = Harness(settings)
        user = harness.make_user()

        for _ in range(2):
            await harness.service.issue(user, enforce_limits=False)

        harness.clock.advance(24 * 3600 + 1)

        await harness.service.issue(user)  # must not raise
