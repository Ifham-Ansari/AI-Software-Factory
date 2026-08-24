"""Email-verification code persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select, update

from factory_core.domain.ids import UserId, VerificationId
from factory_core.persistence.mappers import to_verification, to_verification_row
from factory_core.persistence.models import EmailVerificationRow
from factory_core.persistence.repositories.base import Repository
from factory_core.security.verification import VerificationCode, VerificationStatus


class VerificationRepository(Repository):
    """Stores issued verification codes and their attempt history.

    Not a ``ScopedRepository``: a code is looked up by the user it belongs to, and that
    user is established by the surrounding flow rather than by an ownership scope.
    """

    async def add(self, record: VerificationCode) -> None:
        """Persist a newly issued code."""
        self._session.add(to_verification_row(record))
        await self._session.flush()

    async def latest_for_user(self, user_id: UserId) -> VerificationCode | None:
        """Return the most recently issued code for a user.

        Only the newest matters: issuing a new code supersedes the old one, so an older
        pending row is dead even if nothing has marked it so.
        """
        statement = (
            select(EmailVerificationRow)
            .where(EmailVerificationRow.user_id == user_id)
            .order_by(EmailVerificationRow.issued_at.desc())
            .limit(1)
        )
        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()
        return to_verification(row) if row else None

    async def count_issued_since(self, user_id: UserId, *, since: datetime) -> int:
        """Count codes issued to a user since a cutoff.

        Backs the daily cap. Counted in the database rather than a cache because the cap
        is an abuse control: a cache eviction must not hand someone a fresh budget.
        """
        statement = (
            select(func.count())
            .select_from(EmailVerificationRow)
            .where(
                EmailVerificationRow.user_id == user_id,
                EmailVerificationRow.issued_at >= since,
            )
        )
        result = await self._session.execute(statement)
        return int(result.scalar_one())

    async def record_attempt(self, verification_id: VerificationId) -> int:
        """Increment the attempt counter for a wrong guess.

        Incremented in SQL rather than read-modify-write so two concurrent guesses cannot
        both read the same count and each burn only one attempt between them.

        Returns:
            The attempt count after incrementing.
        """
        statement = (
            update(EmailVerificationRow)
            .where(EmailVerificationRow.id == verification_id)
            .values(attempts=EmailVerificationRow.attempts + 1)
            .returning(EmailVerificationRow.attempts)
        )
        result = await self._session.execute(statement)
        return int(result.scalar_one())

    async def mark(
        self,
        verification_id: VerificationId,
        status: VerificationStatus,
        *,
        now: datetime | None = None,
    ) -> None:
        """Move a code to a terminal state."""
        values: dict[str, Any] = {"status": status.value}
        if status is VerificationStatus.CONSUMED:
            values["consumed_at"] = now or datetime.now(UTC)
        statement = (
            update(EmailVerificationRow)
            .where(EmailVerificationRow.id == verification_id)
            .values(**values)
        )
        await self._session.execute(statement)

    async def invalidate_pending(self, user_id: UserId) -> int:
        """Retire every pending code for a user.

        Called before issuing a replacement, so exactly one code is live at a time. Two
        valid codes would double an attacker's guessing surface for no benefit.

        Returns:
            How many codes were retired.
        """
        statement = (
            update(EmailVerificationRow)
            .where(
                EmailVerificationRow.user_id == user_id,
                EmailVerificationRow.status == VerificationStatus.PENDING.value,
            )
            .values(status=VerificationStatus.EXPIRED.value)
        )
        result = await self._session.execute(statement)
        return int(cast(CursorResult[Any], result).rowcount or 0)

    async def delete_expired(self, *, before: datetime) -> int:
        """Remove codes that expired before a cutoff.

        Housekeeping so the table does not grow without bound.

        Returns:
            How many rows were deleted.
        """
        statement = delete(EmailVerificationRow).where(EmailVerificationRow.expires_at < before)
        result = await self._session.execute(statement)
        return int(cast(CursorResult[Any], result).rowcount or 0)

    @staticmethod
    def day_ago(now: datetime | None = None) -> datetime:
        """The cutoff for the daily issuance cap."""
        return (now or datetime.now(UTC)) - timedelta(days=1)
