"""Authentication service.

Owns account creation, sign-in, refresh-token rotation and sign-out. Session minting is
delegated to :class:`SessionMinter` so sign-in and rotation issue tokens through the same
code path.

The interesting part is :meth:`AuthService.refresh` — see
``factory_core.security.refresh`` for why rotation plus reuse detection is the design,
and :meth:`_handle_reuse` for what happens when a token is presented twice.

Every method here runs inside a caller-supplied unit of work. The service never commits:
the transaction boundary belongs to the caller, so an audit entry and the change it
describes are written atomically or not at all.
"""

from __future__ import annotations

from factory_core.application.auth.minting import SessionMinter
from factory_core.application.auth.schemas import (
    AuthSession,
    RegisterCommand,
    SignInCommand,
)
from factory_core.application.ports import Clock, SystemClock
from factory_core.domain.audit import AuditAction, AuditRequest
from factory_core.domain.ids import TokenFamilyId, new_token_family_id, new_user_id
from factory_core.domain.policies import ensure_active_user
from factory_core.errors import (
    AlreadyExistsError,
    InvalidCredentialsError,
    TokenExpiredError,
    TokenInvalidError,
    TokenReusedError,
)
from factory_core.observability import get_logger
from factory_core.persistence.repositories import (
    AuditRepository,
    RefreshTokenRepository,
    UserRepository,
)
from factory_core.security import (
    AccessTokenIssuer,
    PasswordHasher,
    RefreshTokenStatus,
    hash_refresh_token,
)

logger = get_logger(__name__)


class AuthService:
    """Establishes, refreshes and revokes sessions."""

    def __init__(
        self,
        *,
        users: UserRepository,
        tokens: RefreshTokenRepository,
        audit: AuditRepository,
        hasher: PasswordHasher,
        issuer: AccessTokenIssuer,
        refresh_ttl_seconds: int,
        clock: Clock | None = None,
        request_id: str | None = None,
    ) -> None:
        self._users = users
        self._tokens = tokens
        self._audit = audit
        self._hasher = hasher
        self._clock = clock or SystemClock()
        self._request_id = request_id
        self._minter = SessionMinter(
            tokens=tokens,
            issuer=issuer,
            refresh_ttl_seconds=refresh_ttl_seconds,
            clock=self._clock,
        )

    async def register(self, command: RegisterCommand) -> AuthSession:
        """Create an account and sign the new user in.

        Raises:
            AlreadyExistsError: The email address is already registered.
        """
        if await self._users.email_exists(command.email):
            # Checked explicitly for a clean error; the unique constraint is still the
            # real guarantee against a concurrent duplicate registration.
            raise AlreadyExistsError("An account with that email address already exists.")

        user = await self._users.create(
            user_id=new_user_id(),
            email=command.email,
            display_name=command.display_name,
            password_hash=self._hasher.hash(command.password_value()),
            now=self._clock.now(),
        )
        await self._record(AuditRequest.for_user(AuditAction.USER_REGISTERED, user.id))
        logger.info("auth.registered", user_id=str(user.id))
        session, _ = await self._minter.mint(user, family_id=new_token_family_id())
        return session

    async def sign_in(self, command: SignInCommand) -> AuthSession:
        """Authenticate credentials and start a session.

        Raises:
            InvalidCredentialsError: Email unknown, password wrong, or account suspended.
                All three produce the identical error, so this endpoint cannot be used to
                discover which addresses are registered.
        """
        credentials = await self._users.get_credentials(command.email)

        if credentials is None:
            # Hash anyway so an unknown email costs the same time as a wrong password.
            self._hasher.verify_dummy()
            await self._record(
                AuditRequest(action=AuditAction.USER_SIGN_IN_FAILED, metadata={"reason": "unknown"})
            )
            raise InvalidCredentialsError

        user, password_hash = credentials
        if not self._hasher.verify(password_hash, command.password_value()):
            await self._record(
                AuditRequest.for_user(
                    AuditAction.USER_SIGN_IN_FAILED, user.id, reason="bad_password"
                )
            )
            raise InvalidCredentialsError

        if not user.is_active:
            await self._record(
                AuditRequest.for_user(AuditAction.USER_SIGN_IN_FAILED, user.id, reason="suspended")
            )
            raise InvalidCredentialsError

        if self._hasher.needs_rehash(password_hash):
            # Opportunistic upgrade to current cost parameters, without a password reset.
            await self._users.update_password_hash(
                user.id, self._hasher.hash(command.password_value())
            )

        await self._record(AuditRequest.for_user(AuditAction.USER_SIGNED_IN, user.id))
        logger.info("auth.signed_in", user_id=str(user.id))
        session, _ = await self._minter.mint(user, family_id=new_token_family_id())
        return session

    async def refresh(self, refresh_token: str) -> AuthSession:
        """Exchange a refresh token for a new session, rotating the token.

        Raises:
            TokenInvalidError: The token is unknown.
            TokenReusedError: The token was already used or revoked. A rotated token being
                replayed revokes the whole family.
            TokenExpiredError: The token is past its expiry.
        """
        record = await self._tokens.get_by_hash(hash_refresh_token(refresh_token))
        if record is None:
            raise TokenInvalidError

        if record.status is not RefreshTokenStatus.ACTIVE:
            await self._handle_reuse(record.family_id, record.status)

        now = self._clock.now()
        if record.is_expired(now=now):
            raise TokenExpiredError

        user = await self._users.get_by_id(record.user_id)
        if user is None:
            raise TokenInvalidError
        ensure_active_user(user)

        # Rotate: issue the successor inside the same family, then retire the presented
        # token with a pointer to its replacement.
        session, successor_id = await self._minter.mint(user, family_id=record.family_id)
        await self._tokens.mark_rotated(record.id, replaced_by=successor_id, now=now)
        await self._record(AuditRequest.for_user(AuditAction.TOKEN_REFRESHED, user.id))
        return session

    async def sign_out(self, refresh_token: str) -> None:
        """Revoke a session.

        Succeeds silently for an unknown token: sign-out is idempotent, and reporting
        whether a token existed would leak information to an unauthenticated caller.
        """
        record = await self._tokens.get_by_hash(hash_refresh_token(refresh_token))
        if record is None:
            return
        await self._tokens.revoke_token(record.id, now=self._clock.now())
        await self._record(AuditRequest.for_user(AuditAction.USER_SIGNED_OUT, record.user_id))
        logger.info("auth.signed_out", user_id=str(record.user_id))

    async def _handle_reuse(self, family_id: TokenFamilyId, status: RefreshTokenStatus) -> None:
        """React to a token that is no longer active being presented.

        A *rotated* token means someone still holds a copy that was already exchanged —
        theft, or a cloned client. We cannot tell the attacker from the victim, so the
        whole family is revoked and both must sign in again. That is the entire value of
        rotation: a stolen token is usable at most once, and the attempt is recorded.

        A *revoked* token is already dead (an earlier reuse, or a sign-out) and needs no
        action beyond refusal.

        Raises:
            TokenReusedError: Always. This method never returns normally.
        """
        if status is RefreshTokenStatus.ROTATED:
            revoked = await self._tokens.revoke_family(family_id, now=self._clock.now())
            await self._record(
                AuditRequest(
                    action=AuditAction.TOKEN_REUSE_DETECTED,
                    metadata={"family_id": str(family_id), "revoked_count": revoked},
                )
            )
            logger.warning(
                "auth.token_reuse_detected",
                family_id=str(family_id),
                revoked_count=revoked,
            )
        raise TokenReusedError

    async def _record(self, request: AuditRequest) -> None:
        await self._audit.record(request, request_id=self._request_id, now=self._clock.now())
