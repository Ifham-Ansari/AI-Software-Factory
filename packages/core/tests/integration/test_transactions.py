"""Transaction and session behaviour against a real database."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from factory_core.domain.ids import new_project_id, new_user_id
from factory_core.errors import AlreadyExistsError
from factory_core.persistence import (
    ProjectRepository,
    UserRepository,
    create_session_factory,
    read_only_session,
    unit_of_work,
)

pytestmark = pytest.mark.integration


class TestUnitOfWork:
    async def test_commits_on_success(self, engine: AsyncEngine) -> None:
        factory = create_session_factory(engine)

        async with unit_of_work(factory) as session:
            user = await UserRepository(session).create(
                user_id=new_user_id(),
                email="ada@example.com",
                display_name="Ada",
                password_hash="$argon2id$fake",
            )
            user_id = user.id

        async with read_only_session(factory) as session:
            assert await UserRepository(session).get_by_id(user_id) is not None

    @pytest.mark.failure
    async def test_rolls_back_on_error(self, engine: AsyncEngine) -> None:
        """A handler that raises halfway must not leave a partial write behind."""
        factory = create_session_factory(engine)
        user_id = new_user_id()

        with pytest.raises(RuntimeError):
            async with unit_of_work(factory) as session:
                await UserRepository(session).create(
                    user_id=user_id,
                    email="ada@example.com",
                    display_name="Ada",
                    password_hash="$argon2id$fake",
                )
                raise RuntimeError("handler failed after writing")

        async with read_only_session(factory) as session:
            assert await UserRepository(session).get_by_id(user_id) is None

    @pytest.mark.failure
    async def test_multi_write_rollback_is_atomic(self, engine: AsyncEngine) -> None:
        """The user and their project must both land, or neither."""
        factory = create_session_factory(engine)
        user_id = new_user_id()

        with pytest.raises(RuntimeError):
            async with unit_of_work(factory) as session:
                await UserRepository(session).create(
                    user_id=user_id,
                    email="ada@example.com",
                    display_name="Ada",
                    password_hash="$argon2id$fake",
                )
                await ProjectRepository(session, owner_id=user_id).create(
                    project_id=new_project_id(),
                    name="Mine",
                    slug="mine",
                    description="",
                )
                raise RuntimeError("failed at the end")

        async with read_only_session(factory) as session:
            assert await UserRepository(session).get_by_id(user_id) is None

    @pytest.mark.failure
    async def test_constraint_violation_becomes_a_typed_error(self, engine: AsyncEngine) -> None:
        """Callers above persistence must not need to import SQLAlchemy to handle this."""
        factory = create_session_factory(engine)

        async with unit_of_work(factory) as session:
            await UserRepository(session).create(
                user_id=new_user_id(),
                email="ada@example.com",
                display_name="Ada",
                password_hash="$argon2id$fake",
            )

        with pytest.raises(AlreadyExistsError, match="email"):
            async with unit_of_work(factory) as session:
                await UserRepository(session).create(
                    user_id=new_user_id(),
                    email="ada@example.com",
                    display_name="Someone Else",
                    password_hash="$argon2id$fake",
                )


class TestConcurrency:
    async def test_parallel_writes_each_commit(self, engine: AsyncEngine) -> None:
        """Sessions are per-request; concurrent requests must not interfere."""
        factory = create_session_factory(engine)

        async def create(index: int) -> None:
            async with unit_of_work(factory) as session:
                await UserRepository(session).create(
                    user_id=new_user_id(),
                    email=f"user{index}@example.com",
                    display_name=f"User {index}",
                    password_hash="$argon2id$fake",
                )

        await asyncio.gather(*(create(index) for index in range(5)))

        async with read_only_session(factory) as session:
            repo = UserRepository(session)
            for index in range(5):
                assert await repo.get_by_email(f"user{index}@example.com") is not None

    @pytest.mark.failure
    async def test_concurrent_duplicate_registration_is_rejected(self, engine: AsyncEngine) -> None:
        """Exactly one of two racing registrations may win."""
        factory = create_session_factory(engine)

        async def create() -> bool:
            try:
                async with unit_of_work(factory) as session:
                    await UserRepository(session).create(
                        user_id=new_user_id(),
                        email="contested@example.com",
                        display_name="Contender",
                        password_hash="$argon2id$fake",
                    )
            except AlreadyExistsError:
                return False
            return True

        results = await asyncio.gather(create(), create(), return_exceptions=True)

        assert sum(1 for outcome in results if outcome is True) == 1
