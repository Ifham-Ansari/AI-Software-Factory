"""Authentication service behaviour.

Covers registration, sign-in, rotation and — the part that matters most — refresh-token
reuse detection.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from factory_core.application.auth import AuthService, RegisterCommand, SignInCommand
from factory_core.application.ports import FrozenClock
from factory_core.domain.audit import AuditAction
from factory_core.errors import (
    AlreadyExistsError,
    InvalidCredentialsError,
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

    async def register(self, email: str = EMAIL, password: str = PASSWORD):  # type: ignore[no-untyped-def]
        return await self.service.register(
            RegisterCommand(email=email, password=SecretStr(password), display_name="Ada Lovelace")
        )


@pytest.fixture
def harness(password_hasher: PasswordHasher, token_issuer: AccessTokenIssuer) -> Harness:
    return Harness(password_hasher, token_issuer)


class TestRegistration:
    async def test_creates_account_and_signs_in(self, harness: Harness) -> None:
        session = await harness.register()

        assert session.user.email == EMAIL
        assert session.access_token
        assert session.refresh_token
        assert AuditAction.USER_REGISTERED in harness.audit.actions()

    async def test_password_is_hashed_not_stored(self, harness: Harness) -> None:
        session = await harness.register()

        stored = harness.users.hashes[session.user.id]
        assert stored != PASSWORD
        assert stored.startswith("$argon2id$")

    async def test_duplicate_email_rejected(self, harness: Harness) -> None:
        await harness.register()

        with pytest.raises(AlreadyExistsError):
            await harness.register()

    async def test_email_is_normalised(self, harness: Harness) -> None:
        """Registering with different casing must not create a second account."""
        await harness.register(email="Ada@Example.COM")

        with pytest.raises(AlreadyExistsError):
            await harness.register(email="ada@example.com")


class TestSignIn:
    async def test_correct_credentials_start_a_session(self, harness: Harness) -> None:
        await harness.register()

        session = await harness.service.sign_in(
            SignInCommand(email=EMAIL, password=SecretStr(PASSWORD))
        )

        assert session.user.email == EMAIL
        assert AuditAction.USER_SIGNED_IN in harness.audit.actions()

    @pytest.mark.failure
    async def test_wrong_password_rejected(self, harness: Harness) -> None:
        await harness.register()

        with pytest.raises(InvalidCredentialsError):
            await harness.service.sign_in(
                SignInCommand(email=EMAIL, password=SecretStr("wrong-password-entirely"))
            )
        assert AuditAction.USER_SIGN_IN_FAILED in harness.audit.actions()

    @pytest.mark.failure
    @pytest.mark.security
    async def test_unknown_email_is_indistinguishable(self, harness: Harness) -> None:
        """Both failures must raise the same error, or the endpoint enumerates accounts."""
        await harness.register()

        with pytest.raises(InvalidCredentialsError) as unknown:
            await harness.service.sign_in(
                SignInCommand(email="nobody@example.com", password=SecretStr(PASSWORD))
            )
        with pytest.raises(InvalidCredentialsError) as wrong:
            await harness.service.sign_in(
                SignInCommand(email=EMAIL, password=SecretStr("wrong-password-entirely"))
            )

        assert unknown.value.message == wrong.value.message
        assert unknown.value.code == wrong.value.code

    @pytest.mark.security
    async def test_suspended_account_cannot_sign_in(self, harness: Harness) -> None:
        session = await harness.register()
        harness.users.suspend(session.user.id)

        with pytest.raises(InvalidCredentialsError):
            await harness.service.sign_in(SignInCommand(email=EMAIL, password=SecretStr(PASSWORD)))

    async def test_each_sign_in_starts_a_new_family(self, harness: Harness) -> None:
        """Signing in on a second device must not be treated as token theft."""
        await harness.register()
        await harness.service.sign_in(SignInCommand(email=EMAIL, password=SecretStr(PASSWORD)))

        families = {t.family_id for t in harness.tokens.tokens.values()}
        assert len(families) == 2


class TestRefreshRotation:
    async def test_refresh_issues_a_new_token(self, harness: Harness) -> None:
        session = await harness.register()

        refreshed = await harness.service.refresh(session.refresh_token)

        assert refreshed.refresh_token != session.refresh_token
        assert refreshed.user.id == session.user.id
        assert AuditAction.TOKEN_REFRESHED in harness.audit.actions()

    async def test_rotation_stays_in_the_same_family(self, harness: Harness) -> None:
        session = await harness.register()
        await harness.service.refresh(session.refresh_token)

        families = {t.family_id for t in harness.tokens.tokens.values()}
        assert len(families) == 1

    async def test_old_token_links_to_its_successor(self, harness: Harness) -> None:
        """The chain is what makes a compromised family traceable after the fact."""
        session = await harness.register()
        await harness.service.refresh(session.refresh_token)

        rotated = [t for t in harness.tokens.tokens.values() if t.replaced_by_id is not None]
        assert len(rotated) == 1
        assert rotated[0].replaced_by_id in harness.tokens.tokens

    async def test_refresh_chain_works_repeatedly(self, harness: Harness) -> None:
        session = await harness.register()

        token = session.refresh_token
        for _ in range(5):
            token = (await harness.service.refresh(token)).refresh_token

        assert token


class TestSignOut:
    async def test_revokes_the_session(self, harness: Harness) -> None:
        session = await harness.register()

        await harness.service.sign_out(session.refresh_token)

        with pytest.raises(TokenReusedError):
            await harness.service.refresh(session.refresh_token)
        assert AuditAction.USER_SIGNED_OUT in harness.audit.actions()

    async def test_unknown_token_succeeds_silently(self, harness: Harness) -> None:
        """Idempotent, and must not reveal whether a token was real."""
        await harness.service.sign_out("never-existed")

    async def test_signing_out_twice_is_safe(self, harness: Harness) -> None:
        session = await harness.register()

        await harness.service.sign_out(session.refresh_token)
        await harness.service.sign_out(session.refresh_token)
