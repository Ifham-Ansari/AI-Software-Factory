"""Session minting.

Creating a session is a separate concern from deciding whether someone deserves one.
``AuthService`` answers "are these credentials good?"; this answers "issue the tokens and
record them". Keeping them apart means the rotation path and the sign-in path mint
sessions through exactly one piece of code, so they cannot drift.
"""

from __future__ import annotations

from factory_core.application.auth.schemas import AuthSession
from factory_core.application.ports import Clock
from factory_core.domain.entities import User
from factory_core.domain.ids import TokenFamilyId, TokenId, new_token_id
from factory_core.persistence.repositories import RefreshTokenRepository
from factory_core.security import AccessTokenIssuer, generate_refresh_token


class SessionMinter:
    """Issues access and refresh tokens for an authenticated user."""

    def __init__(
        self,
        *,
        tokens: RefreshTokenRepository,
        issuer: AccessTokenIssuer,
        refresh_ttl_seconds: int,
        clock: Clock,
    ) -> None:
        self._tokens = tokens
        self._issuer = issuer
        self._refresh_ttl = refresh_ttl_seconds
        self._clock = clock

    async def mint(self, user: User, *, family_id: TokenFamilyId) -> tuple[AuthSession, TokenId]:
        """Create a session for a user.

        Args:
            user: The authenticated user.
            family_id: The session family. A fresh sign-in starts a new one; a rotation
                keeps the existing one so reuse detection can revoke the whole chain.

        Returns:
            The session, and the identifier of the refresh token just issued. Rotation
            needs that identifier to link the retired token to its successor; returning it
            keeps the data flow explicit rather than stashing it on the instance.
        """
        now = self._clock.now()
        token_id = new_token_id()
        issued = generate_refresh_token(
            user_id=user.id,
            family_id=family_id,
            token_id=token_id,
            ttl_seconds=self._refresh_ttl,
            now=now,
        )
        await self._tokens.add(issued.record)
        session = AuthSession(
            user=user,
            access_token=self._issuer.issue(user.id, now=now),
            refresh_token=issued.token,
            access_expires_in=self._issuer.ttl_seconds,
            refresh_expires_in=self._refresh_ttl,
        )
        return session, token_id
