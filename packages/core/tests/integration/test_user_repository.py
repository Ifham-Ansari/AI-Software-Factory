"""User persistence against a real PostgreSQL database."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from factory_core.domain.ids import (
    UserId,
    new_user_id,
)
from factory_core.persistence import (
    UserRepository,
)

pytestmark = pytest.mark.integration


async def _make_user(session: AsyncSession, email: str = "ada@example.com") -> UserId:
    user = await UserRepository(session).create(
        user_id=new_user_id(),
        email=email,
        display_name="Ada Lovelace",
        password_hash="$argon2id$fake",
    )
    return user.id


class TestUserRepository:
    async def test_create_and_load(self, session: AsyncSession) -> None:
        repo = UserRepository(session)
        user_id = await _make_user(session)

        loaded = await repo.get_by_id(user_id)

        assert loaded is not None
        assert loaded.email == "ada@example.com"

    async def test_get_by_email(self, session: AsyncSession) -> None:
        await _make_user(session)

        assert await UserRepository(session).get_by_email("ada@example.com") is not None

    async def test_entity_never_carries_the_hash(self, session: AsyncSession) -> None:
        """Enforced by the mapper: there is no code path from row to entity for a hash."""
        user_id = await _make_user(session)

        user = await UserRepository(session).get_by_id(user_id)

        assert user is not None
        assert "password" not in user.model_dump()

    async def test_credentials_lookup_returns_the_hash(self, session: AsyncSession) -> None:
        await _make_user(session)

        result = await UserRepository(session).get_credentials("ada@example.com")

        assert result is not None
        assert result[1] == "$argon2id$fake"

    @pytest.mark.failure
    async def test_duplicate_email_violates_the_constraint(self, session: AsyncSession) -> None:
        """The unique index is the real guarantee, not the service-level pre-check."""
        from sqlalchemy.exc import IntegrityError

        await _make_user(session)

        with pytest.raises(IntegrityError):
            await _make_user(session)

    async def test_password_hash_update(self, session: AsyncSession) -> None:
        repo = UserRepository(session)
        user_id = await _make_user(session)

        await repo.update_password_hash(user_id, "$argon2id$upgraded")

        credentials = await repo.get_credentials("ada@example.com")
        assert credentials is not None
        assert credentials[1] == "$argon2id$upgraded"
