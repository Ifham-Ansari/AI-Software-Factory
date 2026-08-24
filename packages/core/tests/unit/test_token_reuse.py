"""Refresh-token reuse detection.

The property that makes rotation worth doing: a stolen token is usable at most once,
the attempt is detected, and the whole compromised session chain dies.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from factory_core.application.auth import AuthService, SignInCommand
from factory_core.application.ports import FrozenClock
from factory_core.domain.audit import AuditAction
from factory_core.errors import (
    TokenExpiredError,
    TokenInvalidError,
    TokenReusedError,
)
from factory_core.security import AccessTokenIssuer, PasswordHasher
from factory_core.testing import (
    FakeAuditRepository,
    FakeRefreshTokenRepository,
    FakeUserRepository,
)

pytestmark = pytest.mark.unit

EMAIL = "ada@example.com"
PASSWORD = "a-sufficiently-long-passphrase"
REFRESH_TTL = 2_592_000


class Harness:
    """Everything an ``AuthService`` needs, with the collaborators kept reachable."""

    def __init__(self, hasher: PasswordHasher, issuer: AccessTokenIssuer) -> None:
        self.users = FakeUserRepository()
        self.tokens = FakeRefreshTokenRepository()
        self.audit = FakeAuditRepository()
        self.clock = FrozenClock(datetime(2026, 1, 15, 12, 0, tzinfo=UTC))
        self.service = AuthService(
            users=self.users,  # type: ignore[arg-type]
            tokens=self.tokens,  # type: ignore[arg-type]
            audit=self.audit,  # type: ignore[arg-type]
            hasher=hasher,
            issuer=issuer,
            refresh_ttl_seconds=REFRESH_TTL,
            clock=self.clock,
            request_id="test-request",
        )

    async def register_and_sign_in(self, email: str = EMAIL, password: str = PASSWORD):  # type: ignore[no-untyped-def]
        """Register, verify without a real code, and sign in for a session.

        The verification flow itself is exercised in ``test_email_verification.py``; this
        suite only needs a usable, signed-in account.
        """
        from factory_core.application.auth import RegisterCommand

        user = await self.service.register(
            RegisterCommand(email=email, password=SecretStr(password), display_name="Ada")
        )
        self.users.verify(user.id)
        return await self.service.sign_in(SignInCommand(email=email, password=SecretStr(password)))

    async def sign_in(self, email: str = EMAIL, password: str = PASSWORD):  # type: ignore[no-untyped-def]
        return await self.service.sign_in(SignInCommand(email=email, password=SecretStr(password)))


@pytest.fixture
def harness(password_hasher: PasswordHasher, token_issuer: AccessTokenIssuer) -> Harness:
    return Harness(password_hasher, token_issuer)


@pytest.mark.security
@pytest.mark.failure
class TestReuseDetection:
    """The property that makes rotation worth doing."""

    async def test_reusing_a_rotated_token_is_refused(self, harness: Harness) -> None:
        session = await harness.register_and_sign_in()
        await harness.service.refresh(session.refresh_token)

        with pytest.raises(TokenReusedError):
            await harness.service.refresh(session.refresh_token)

    async def test_reuse_revokes_the_entire_family(self, harness: Harness) -> None:
        """A stolen token must be usable at most once, and must cost the thief the session."""
        session = await harness.register_and_sign_in()
        current = await harness.service.refresh(session.refresh_token)

        with pytest.raises(TokenReusedError):
            await harness.service.refresh(session.refresh_token)

        # The legitimate holder's current token is now dead too. We cannot tell the
        # victim from the thief, so both must re-authenticate.
        with pytest.raises(TokenReusedError):
            await harness.service.refresh(current.refresh_token)

    async def test_reuse_is_audited(self, harness: Harness) -> None:
        session = await harness.register_and_sign_in()
        await harness.service.refresh(session.refresh_token)

        with pytest.raises(TokenReusedError):
            await harness.service.refresh(session.refresh_token)

        assert AuditAction.TOKEN_REUSE_DETECTED in harness.audit.actions()

    async def test_other_sessions_survive_a_revoked_family(self, harness: Harness) -> None:
        """Revocation must be scoped to the compromised family, not the whole account."""
        first = await harness.register_and_sign_in()
        second = await harness.sign_in()
        await harness.service.refresh(first.refresh_token)

        with pytest.raises(TokenReusedError):
            await harness.service.refresh(first.refresh_token)

        # The other device is untouched.
        assert await harness.service.refresh(second.refresh_token)

    async def test_unknown_token_rejected(self, harness: Harness) -> None:
        with pytest.raises(TokenInvalidError):
            await harness.service.refresh("not-a-real-token")

    async def test_expired_token_rejected(self, harness: Harness) -> None:
        session = await harness.register_and_sign_in()
        harness.clock.advance(REFRESH_TTL + 1)

        with pytest.raises(TokenExpiredError):
            await harness.service.refresh(session.refresh_token)
