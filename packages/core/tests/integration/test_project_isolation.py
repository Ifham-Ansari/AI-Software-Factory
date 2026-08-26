"""Owner scoping in the generated SQL — the central security property.

Fakes can prove the service respects scoping. Only a real database proves the SQL does.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from factory_core.domain.ids import (
    UserId,
    new_project_id,
    new_user_id,
)
from factory_core.domain.pagination import PageRequest
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


@pytest.mark.security
class TestProjectIsolationInSql:
    """The property fakes cannot prove: the generated SQL filters by owner."""

    async def test_get_is_scoped(self, session: AsyncSession) -> None:
        owner = await _make_user(session, "owner@example.com")
        stranger = await _make_user(session, "stranger@example.com")

        project = await ProjectRepository(session, owner_id=owner).create(
            project_id=new_project_id(), name="Private", slug="private", description=""
        )

        assert await ProjectRepository(session, owner_id=stranger).get(project.id) is None
        assert await ProjectRepository(session, owner_id=owner).get(project.id) is not None

    async def test_list_is_scoped(self, session: AsyncSession) -> None:
        owner = await _make_user(session, "owner@example.com")
        stranger = await _make_user(session, "stranger@example.com")

        await ProjectRepository(session, owner_id=owner).create(
            project_id=new_project_id(), name="Mine", slug="mine", description=""
        )

        page = await ProjectRepository(session, owner_id=stranger).list(PageRequest())

        assert page.total == 0

    async def test_update_is_scoped(self, session: AsyncSession) -> None:
        owner = await _make_user(session, "owner@example.com")
        stranger = await _make_user(session, "stranger@example.com")
        project = await ProjectRepository(session, owner_id=owner).create(
            project_id=new_project_id(), name="Mine", slug="mine", description=""
        )

        result = await ProjectRepository(session, owner_id=stranger).update(
            project.id, name="Hijacked"
        )

        assert result is None
        unchanged = await ProjectRepository(session, owner_id=owner).get(project.id)
        assert unchanged is not None
        assert unchanged.name == "Mine"

    async def test_delete_is_scoped(self, session: AsyncSession) -> None:
        owner = await _make_user(session, "owner@example.com")
        stranger = await _make_user(session, "stranger@example.com")
        project = await ProjectRepository(session, owner_id=owner).create(
            project_id=new_project_id(), name="Mine", slug="mine", description=""
        )

        assert await ProjectRepository(session, owner_id=stranger).delete(project.id) is False
        assert await ProjectRepository(session, owner_id=owner).get(project.id) is not None

    async def test_archive_is_scoped(self, session: AsyncSession) -> None:
        owner = await _make_user(session, "owner@example.com")
        stranger = await _make_user(session, "stranger@example.com")
        project = await ProjectRepository(session, owner_id=owner).create(
            project_id=new_project_id(), name="Mine", slug="mine", description=""
        )

        assert await ProjectRepository(session, owner_id=stranger).archive(project.id) is None

    async def test_restore_is_scoped(self, session: AsyncSession) -> None:
        """Restoring is a write, and writes are scoped by owner like every other one.

        Worth asserting separately from archiving: restore is reached through a different
        policy (an archived project refuses ordinary writes), so it is exactly the kind of
        exception where a scope check gets forgotten.
        """
        owner = await _make_user(session, "owner@example.com")
        stranger = await _make_user(session, "stranger@example.com")
        repository = ProjectRepository(session, owner_id=owner)
        project = await repository.create(
            project_id=new_project_id(), name="Mine", slug="mine", description=""
        )
        await repository.archive(project.id)

        assert await ProjectRepository(session, owner_id=stranger).restore(project.id) is None
        still_archived = await repository.get(project.id)
        assert still_archived is not None
        assert still_archived.is_archived

    async def test_repository_requires_a_scope(self, session: AsyncSession) -> None:
        """An unscoped repository would return every user's rows."""
        with pytest.raises(ValueError, match="owner_id"):
            ProjectRepository(session, owner_id=None)  # type: ignore[arg-type]
