"""Refresh-token persistence, including family revocation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select, update

from factory_core.domain.ids import TokenFamilyId, TokenId, UserId
from factory_core.persistence.mappers import to_refresh_token, to_refresh_token_row
from factory_core.persistence.models import RefreshTokenRow
from factory_core.persistence.repositories.base import Repository
from factory_core.security.refresh import RefreshTokenRecord, RefreshTokenStatus


class RefreshTokenRepository(Repository):
    """Stores issued refresh tokens and their rotation history.

    Not a ``ScopedRepository``: a token is looked up by digest *before* the owner is
    known, which is the whole point — the digest is what identifies the session.
    Authorization is the digest itself.
    """

    async def add(self, record: RefreshTokenRecord) -> None:
        """Persist a newly issued token."""
        self._session.add(to_refresh_token_row(record))
        await self._session.flush()

    async def get_by_hash(self, token_hash: str) -> RefreshTokenRecord | None:
        """Find a token by its stored digest."""
        statement = select(RefreshTokenRow).where(RefreshTokenRow.token_hash == token_hash)
        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()
        return to_refresh_token(row) if row else None

    async def mark_rotated(
        self,
        token_id: TokenId,
        *,
        replaced_by: TokenId,
        now: datetime | None = None,
    ) -> None:
        """Retire a token that has just been exchanged for a successor.

        A rotated token is no longer usable, and presenting it again is what reuse
        detection keys on.
        """
        timestamp = now or datetime.now(UTC)
        statement = (
            update(RefreshTokenRow)
            .where(RefreshTokenRow.id == token_id)
            .values(
                status=RefreshTokenStatus.ROTATED.value,
                rotated_at=timestamp,
                replaced_by_id=replaced_by,
            )
        )
        await self._session.execute(statement)

    async def revoke_family(self, family_id: TokenFamilyId, *, now: datetime | None = None) -> int:
        """Revoke every token in a family.

        Called when a rotated token is presented a second time. The token was either
        stolen or cloned, and we cannot tell the thief from the victim, so the whole
        session chain dies and both must sign in again.

        Returns:
            How many tokens were revoked.
        """
        timestamp = now or datetime.now(UTC)
        statement = (
            update(RefreshTokenRow)
            .where(
                RefreshTokenRow.family_id == family_id,
                RefreshTokenRow.status != RefreshTokenStatus.REVOKED.value,
            )
            .values(status=RefreshTokenStatus.REVOKED.value, revoked_at=timestamp)
        )
        result = await self._session.execute(statement)
        return int(cast(CursorResult[Any], result).rowcount or 0)

    async def revoke_token(self, token_id: TokenId, *, now: datetime | None = None) -> None:
        """Revoke a single token, as happens on an explicit sign-out."""
        timestamp = now or datetime.now(UTC)
        statement = (
            update(RefreshTokenRow)
            .where(RefreshTokenRow.id == token_id)
            .values(status=RefreshTokenStatus.REVOKED.value, revoked_at=timestamp)
        )
        await self._session.execute(statement)

    async def revoke_all_for_user(self, user_id: UserId, *, now: datetime | None = None) -> int:
        """Revoke every active session for a user.

        Returns:
            How many tokens were revoked.
        """
        timestamp = now or datetime.now(UTC)
        statement = (
            update(RefreshTokenRow)
            .where(
                RefreshTokenRow.user_id == user_id,
                RefreshTokenRow.status != RefreshTokenStatus.REVOKED.value,
            )
            .values(status=RefreshTokenStatus.REVOKED.value, revoked_at=timestamp)
        )
        result = await self._session.execute(statement)
        return int(cast(CursorResult[Any], result).rowcount or 0)

    async def delete_expired(self, *, before: datetime) -> int:
        """Remove tokens that expired before a cutoff.

        Housekeeping so the table does not grow without bound. Revoked-but-unexpired rows
        are deliberately kept: they are what reuse detection consults.

        Returns:
            How many rows were deleted.
        """
        statement = delete(RefreshTokenRow).where(RefreshTokenRow.expires_at < before)
        result = await self._session.execute(statement)
        return int(cast(CursorResult[Any], result).rowcount or 0)
