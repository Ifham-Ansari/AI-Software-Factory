"""Project service behaviour, including per-owner isolation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from factory_core.application.ports import FrozenClock
from factory_core.application.projects import (
    CreateProjectCommand,
    ProjectService,
    UpdateProjectCommand,
)
from factory_core.domain.audit import AuditAction
from factory_core.domain.entities import ProjectStatus
from factory_core.domain.ids import ProjectId, UserId, new_id
from factory_core.errors import AuthorizationError, NotFoundError, ValidationError
from factory_core.testing import FakeAuditRepository, FakeProjectRepository, FakeProjectStore

pytestmark = pytest.mark.unit


class Harness:
    """A project service for one owner over a shared store."""

    def __init__(self, store: FakeProjectStore, owner_id: UserId) -> None:
        self.store = store
        self.audit = FakeAuditRepository()
        self.clock = FrozenClock(datetime(2026, 1, 15, 12, 0, tzinfo=UTC))
        self.service = ProjectService(
            projects=FakeProjectRepository(store, owner_id=owner_id),  # type: ignore[arg-type]
            audit=self.audit,  # type: ignore[arg-type]
            actor_id=owner_id,
            clock=self.clock,
        )


@pytest.fixture
def store() -> FakeProjectStore:
    return FakeProjectStore()


@pytest.fixture
def owner(store: FakeProjectStore, user_id: UserId) -> Harness:
    return Harness(store, user_id)


@pytest.fixture
def stranger(store: FakeProjectStore, other_user_id: UserId) -> Harness:
    """A second user's service over the *same* store, for isolation tests."""
    return Harness(store, other_user_id)


class TestCreate:
    async def test_creates_a_draft_project(self, owner: Harness) -> None:
        project = await owner.service.create(
            CreateProjectCommand(name="Restaurant System", description="POS and inventory.")
        )

        assert project.name == "Restaurant System"
        assert project.slug == "restaurant-system"
        assert project.status is ProjectStatus.DRAFT
        assert AuditAction.PROJECT_CREATED in owner.audit.actions()

    async def test_assigns_ownership_from_scope_not_input(
        self, owner: Harness, user_id: UserId
    ) -> None:
        """Ownership comes from the repository scope; no request field can set it."""
        project = await owner.service.create(CreateProjectCommand(name="Mine"))

        assert project.owner_id == user_id

    async def test_duplicate_name_gets_a_distinct_slug(self, owner: Harness) -> None:
        """Two projects with the same name is a reasonable thing to want."""
        first = await owner.service.create(CreateProjectCommand(name="Inventory"))
        second = await owner.service.create(CreateProjectCommand(name="Inventory"))

        assert first.slug == "inventory"
        assert second.slug == "inventory-2"

    async def test_different_owners_may_share_a_slug(
        self, owner: Harness, stranger: Harness
    ) -> None:
        """Slugs are unique per owner, not globally."""
        mine = await owner.service.create(CreateProjectCommand(name="Inventory"))
        theirs = await stranger.service.create(CreateProjectCommand(name="Inventory"))

        assert mine.slug == theirs.slug == "inventory"

    @pytest.mark.parametrize("name", ["   ", "\t\n"])
    async def test_blank_name_rejected(self, owner: Harness, name: str) -> None:
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            await owner.service.create(CreateProjectCommand(name=name))


class TestRead:
    async def test_owner_can_read_their_project(self, owner: Harness) -> None:
        created = await owner.service.create(CreateProjectCommand(name="Mine"))

        assert (await owner.service.get(created.id)).id == created.id

    @pytest.mark.security
    async def test_stranger_cannot_read(self, owner: Harness, stranger: Harness) -> None:
        created = await owner.service.create(CreateProjectCommand(name="Mine"))

        with pytest.raises(NotFoundError):
            await stranger.service.get(created.id)

    @pytest.mark.security
    async def test_missing_and_forbidden_are_indistinguishable(
        self, owner: Harness, stranger: Harness
    ) -> None:
        created = await owner.service.create(CreateProjectCommand(name="Mine"))

        with pytest.raises(NotFoundError) as forbidden:
            await stranger.service.get(created.id)
        with pytest.raises(NotFoundError) as missing:
            await stranger.service.get(ProjectId(new_id()))

        assert forbidden.value.message == missing.value.message


class TestUpdate:
    async def test_updates_name_and_reslugs(self, owner: Harness) -> None:
        created = await owner.service.create(CreateProjectCommand(name="Old Name"))

        updated = await owner.service.update(created.id, UpdateProjectCommand(name="New Name"))

        assert updated.name == "New Name"
        assert updated.slug == "new-name"
        assert AuditAction.PROJECT_UPDATED in owner.audit.actions()

    async def test_partial_update_leaves_other_fields(self, owner: Harness) -> None:
        created = await owner.service.create(
            CreateProjectCommand(name="Name", description="Original")
        )

        updated = await owner.service.update(
            created.id, UpdateProjectCommand(description="Changed")
        )

        assert updated.name == "Name"
        assert updated.description == "Changed"

    async def test_empty_command_rejected(self, owner: Harness) -> None:
        created = await owner.service.create(CreateProjectCommand(name="Name"))

        with pytest.raises(ValidationError):
            await owner.service.update(created.id, UpdateProjectCommand())

    @pytest.mark.security
    async def test_stranger_cannot_update(self, owner: Harness, stranger: Harness) -> None:
        created = await owner.service.create(CreateProjectCommand(name="Mine"))

        with pytest.raises(NotFoundError):
            await stranger.service.update(created.id, UpdateProjectCommand(name="Hijacked"))

    async def test_archived_project_is_read_only(self, owner: Harness) -> None:
        created = await owner.service.create(CreateProjectCommand(name="Name"))
        await owner.service.archive(created.id)

        with pytest.raises(AuthorizationError):
            await owner.service.update(created.id, UpdateProjectCommand(name="Changed"))


class TestArchiveAndDelete:
    async def test_archive_marks_and_timestamps(self, owner: Harness) -> None:
        created = await owner.service.create(CreateProjectCommand(name="Name"))

        archived = await owner.service.archive(created.id)

        assert archived.status is ProjectStatus.ARCHIVED
        assert archived.archived_at is not None
        assert AuditAction.PROJECT_ARCHIVED in owner.audit.actions()

    async def test_archiving_twice_rejected(self, owner: Harness) -> None:
        created = await owner.service.create(CreateProjectCommand(name="Name"))
        await owner.service.archive(created.id)

        with pytest.raises(AuthorizationError):
            await owner.service.archive(created.id)

    async def test_delete_removes_the_project(self, owner: Harness) -> None:
        created = await owner.service.create(CreateProjectCommand(name="Name"))

        await owner.service.delete(created.id)

        with pytest.raises(NotFoundError):
            await owner.service.get(created.id)

    async def test_audit_survives_the_deleted_project(self, owner: Harness) -> None:
        """The record of a deletion is worthless if it disappears with the row."""
        created = await owner.service.create(CreateProjectCommand(name="Name"))

        await owner.service.delete(created.id)

        assert AuditAction.PROJECT_DELETED in owner.audit.actions()

    @pytest.mark.security
    async def test_stranger_cannot_delete(self, owner: Harness, stranger: Harness) -> None:
        created = await owner.service.create(CreateProjectCommand(name="Mine"))

        with pytest.raises(NotFoundError):
            await stranger.service.delete(created.id)

        assert await owner.service.get(created.id)
