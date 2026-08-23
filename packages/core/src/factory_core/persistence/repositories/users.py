"""User persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from factory_core.domain.entities import User, UserStatus
from factory_core.domain.ids import UserId
from factory_core.persistence.mappers import to_user
from factory_core.persistence.models import UserRow
from factory_core.persistence.repositories.base import Repository


class UserRepository(Repository):
    """Reads and writes accounts.

    Password hashes are handled here and in the authentication service only. The methods
    that return a ``User`` never expose one; the single method that does return a hash
    says so in its name.
    """

    async def get_by_id(self, user_id: UserId) -> User | None:
        """Load a user by identifier."""
        row = await self._session.get(UserRow, user_id)
        return to_user(row) if row else None

    async def get_by_email(self, email: str) -> User | None:
        """Load a user by normalised email address."""
        row = await self._row_by_email(email)
        return to_user(row) if row else None

    async def get_credentials(self, email: str) -> tuple[User, str] | None:
        """Load a user together with their password hash.

        Used only by the sign-in path. Named explicitly so that a reviewer can grep for
        every place a hash is read.

        Returns:
            The user and their stored hash, or ``None`` when no account matches.
        """
        row = await self._row_by_email(email)
        return (to_user(row), row.password_hash) if row else None

    async def email_exists(self, email: str) -> bool:
        """Whether an account already uses this email address."""
        statement = select(UserRow.id).where(UserRow.email == email).limit(1)
        result = await self._session.execute(statement)
        return result.first() is not None

    async def create(
        self,
        *,
        user_id: UserId,
        email: str,
        display_name: str,
        password_hash: str,
        now: datetime | None = None,
    ) -> User:
        """Insert a new account.

        The caller supplies the identifier so it can reference the user in the same
        transaction — in an audit entry, for example — before the row is flushed.

        Raises:
            AlreadyExistsError: The email address is already registered. Raised by the
                unit of work when the unique constraint rejects the insert.
        """
        timestamp = now or datetime.now(UTC)
        row = UserRow(
            id=user_id,
            email=email,
            display_name=display_name,
            password_hash=password_hash,
            status=UserStatus.ACTIVE.value,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._session.add(row)
        await self._session.flush()
        return to_user(row)

    async def update_password_hash(
        self, user_id: UserId, password_hash: str, *, now: datetime | None = None
    ) -> None:
        """Replace a stored password hash.

        Used to upgrade a hash to stronger parameters after a successful sign-in.
        """
        row = await self._session.get(UserRow, user_id)
        if row is None:
            return
        row.password_hash = password_hash
        row.updated_at = now or datetime.now(UTC)
        await self._session.flush()

    async def _row_by_email(self, email: str) -> UserRow | None:
        statement = select(UserRow).where(UserRow.email == email).limit(1)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()
