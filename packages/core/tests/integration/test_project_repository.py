"""Project persistence: constraints, pagination, filtering, cascades."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from factory_core.domain.entities import ProjectStatus
from factory_core.domain.ids import (
    UserId,
    new_project_id,
    new_user_id,
)
from factory_core.domain.pagination import PageRequest, SortDirection
from factory_core.persistence import (
    ProjectRepository,
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


class TestProjectRepository:
    async def test_slug_uniqueness_is_per_owner(self, session: AsyncSession) -> None:
        first = await _make_user(session, "a@example.com")
        second = await _make_user(session, "b@example.com")

        await ProjectRepository(session, owner_id=first).create(
            project_id=new_project_id(), name="Inventory", slug="inventory", description=""
        )
        await ProjectRepository(session, owner_id=second).create(
            project_id=new_project_id(), name="Inventory", slug="inventory", description=""
        )

        assert await ProjectRepository(session, owner_id=first).slug_exists("inventory")
        assert await ProjectRepository(session, owner_id=second).slug_exists("inventory")

    @pytest.mark.failure
    async def test_duplicate_slug_for_one_owner_is_rejected(self, session: AsyncSession) -> None:
        from sqlalchemy.exc import IntegrityError

        owner = await _make_user(session)
        repo = ProjectRepository(session, owner_id=owner)
        await repo.create(
            project_id=new_project_id(), name="Inventory", slug="inventory", description=""
        )

        with pytest.raises(IntegrityError):
            await repo.create(
                project_id=new_project_id(), name="Other", slug="inventory", description=""
            )

    async def test_pagination_and_stable_ordering(self, session: AsyncSession) -> None:
        """Identical sort values must not shuffle between pages."""
        owner = await _make_user(session)
        repo = ProjectRepository(session, owner_id=owner)
        timestamp = datetime.now(UTC)
        for index in range(10):
            await repo.create(
                project_id=new_project_id(),
                name=f"Project {index:02d}",
                slug=f"project-{index:02d}",
                description="",
                now=timestamp,
            )

        first = await repo.list(PageRequest(page=1, page_size=5))
        second = await repo.list(PageRequest(page=2, page_size=5))

        assert first.total == second.total == 10
        assert len({p.id for p in first.items} & {p.id for p in second.items}) == 0

    async def test_search_escapes_wildcards(self, session: AsyncSession) -> None:
        """A user searching for a literal % must not match everything."""
        owner = await _make_user(session)
        repo = ProjectRepository(session, owner_id=owner)
        await repo.create(
            project_id=new_project_id(), name="100% Coverage", slug="a", description=""
        )
        await repo.create(
            project_id=new_project_id(), name="Something Else", slug="b", description=""
        )

        page = await repo.list(PageRequest(), search="100%")

        assert [p.name for p in page.items] == ["100% Coverage"]

    async def test_sorting(self, session: AsyncSession) -> None:
        owner = await _make_user(session)
        repo = ProjectRepository(session, owner_id=owner)
        for name in ("Charlie", "Alpha", "Bravo"):
            await repo.create(
                project_id=new_project_id(),
                name=name,
                slug=name.lower(),
                description="",
            )

        page = await repo.list(PageRequest(sort_by="name", direction=SortDirection.ASC))

        assert [p.name for p in page.items] == ["Alpha", "Bravo", "Charlie"]

    async def test_status_filter(self, session: AsyncSession) -> None:
        owner = await _make_user(session)
        repo = ProjectRepository(session, owner_id=owner)
        keep = await repo.create(
            project_id=new_project_id(), name="Active", slug="active", description=""
        )
        drop = await repo.create(
            project_id=new_project_id(), name="Old", slug="old", description=""
        )
        await repo.archive(drop.id)

        page = await repo.list(PageRequest(), status=ProjectStatus.DRAFT)

        assert [p.id for p in page.items] == [keep.id]

    async def test_cascade_delete_with_owner(self, session: AsyncSession) -> None:
        """Deleting a user must not orphan their projects."""
        from sqlalchemy import delete, select

        from factory_core.persistence.models import ProjectRow, UserRow

        owner = await _make_user(session)
        await ProjectRepository(session, owner_id=owner).create(
            project_id=new_project_id(), name="Mine", slug="mine", description=""
        )

        await session.execute(delete(UserRow).where(UserRow.id == owner))
        await session.flush()

        remaining = await session.execute(select(ProjectRow).where(ProjectRow.owner_id == owner))
        assert remaining.scalars().all() == []
