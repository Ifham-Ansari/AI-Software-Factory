"""Refresh-token persistence and family revocation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from factory_core.domain.ids import (
    UserId,
    new_token_family_id,
    new_token_id,
    new_user_id,
)
from factory_core.persistence import (
    RefreshTokenRepository,
    UserRepository,
)
from factory_core.security import RefreshTokenStatus, generate_refresh_token

pytestmark = pytest.mark.integration


async def _make_user(session: AsyncSession, email: str = "ada@example.com") -> UserId:
    user = await UserRepository(session).create(
        user_id=new_user_id(),
        email=email,
        display_name="Ada Lovelace",
        password_hash="$argon2id$fake",
    )
    return user.id


class TestRefreshTokenRepository:
    async def test_round_trip_by_hash(self, session: AsyncSession) -> None:
        owner = await _make_user(session)
        repo = RefreshTokenRepository(session)
        issued = generate_refresh_token(
            user_id=owner,
            family_id=new_token_family_id(),
            token_id=new_token_id(),
            ttl_seconds=3600,
        )

        await repo.add(issued.record)

        found = await repo.get_by_hash(issued.record.token_hash)
        assert found is not None
        assert found.id == issued.record.id

    async def test_family_revocation(self, session: AsyncSession) -> None:
        owner = await _make_user(session)
        repo = RefreshTokenRepository(session)
        family = new_token_family_id()
        for _ in range(3):
            issued = generate_refresh_token(
                user_id=owner,
                family_id=family,
                token_id=new_token_id(),
                ttl_seconds=3600,
            )
            await repo.add(issued.record)

        revoked = await repo.revoke_family(family)

        assert revoked == 3

    async def test_revocation_is_scoped_to_the_family(self, session: AsyncSession) -> None:
        """Revoking one compromised session must not sign the user out everywhere."""
        owner = await _make_user(session)
        repo = RefreshTokenRepository(session)
        compromised = new_token_family_id()
        other = new_token_family_id()
        for family in (compromised, other):
            issued = generate_refresh_token(
                user_id=owner,
                family_id=family,
                token_id=new_token_id(),
                ttl_seconds=3600,
            )
            await repo.add(issued.record)
            if family is other:
                survivor_hash = issued.record.token_hash

        await repo.revoke_family(compromised)

        survivor = await repo.get_by_hash(survivor_hash)
        assert survivor is not None
        assert survivor.status is RefreshTokenStatus.ACTIVE

    async def test_expired_cleanup(self, session: AsyncSession) -> None:
        owner = await _make_user(session)
        repo = RefreshTokenRepository(session)
        stale = generate_refresh_token(
            user_id=owner,
            family_id=new_token_family_id(),
            token_id=new_token_id(),
            ttl_seconds=60,
            now=datetime.now(UTC) - timedelta(days=2),
        )
        await repo.add(stale.record)

        deleted = await repo.delete_expired(before=datetime.now(UTC))

        assert deleted == 1
