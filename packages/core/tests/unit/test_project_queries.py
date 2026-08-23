"""Project listing: filtering, searching, sorting and pagination."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from factory_core.application.ports import FrozenClock
from factory_core.application.projects import (
    CreateProjectCommand,
    ProjectQuery,
    ProjectService,
)
from factory_core.domain.entities import ProjectStatus
from factory_core.domain.ids import UserId
from factory_core.domain.pagination import PageRequest, SortDirection
from factory_core.errors import ValidationError
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


class TestList:
    async def test_lists_only_the_owner_s_projects(self, owner: Harness, stranger: Harness) -> None:
        await owner.service.create(CreateProjectCommand(name="Mine A"))
        await owner.service.create(CreateProjectCommand(name="Mine B"))
        await stranger.service.create(CreateProjectCommand(name="Theirs"))

        page = await owner.service.list(ProjectQuery())

        assert page.total == 2
        assert {p.name for p in page.items} == {"Mine A", "Mine B"}

    async def test_pagination(self, owner: Harness) -> None:
        for index in range(5):
            await owner.service.create(CreateProjectCommand(name=f"Project {index}"))

        page = await owner.service.list(ProjectQuery(page=PageRequest(page=2, page_size=2)))

        assert len(page.items) == 2
        assert page.total == 5
        assert page.total_pages == 3
        assert page.has_next and page.has_previous

    async def test_filter_by_status(self, owner: Harness) -> None:
        keep = await owner.service.create(CreateProjectCommand(name="Active"))
        drop = await owner.service.create(CreateProjectCommand(name="Old"))
        await owner.service.archive(drop.id)

        page = await owner.service.list(ProjectQuery(status=ProjectStatus.DRAFT))

        assert [p.id for p in page.items] == [keep.id]

    async def test_search_by_name(self, owner: Harness) -> None:
        await owner.service.create(CreateProjectCommand(name="Restaurant System"))
        await owner.service.create(CreateProjectCommand(name="Inventory Tracker"))

        page = await owner.service.list(ProjectQuery(search="restaurant"))

        assert [p.name for p in page.items] == ["Restaurant System"]

    async def test_sorting_by_name(self, owner: Harness) -> None:
        for name in ("Charlie", "Alpha", "Bravo"):
            await owner.service.create(CreateProjectCommand(name=name))

        page = await owner.service.list(
            ProjectQuery(page=PageRequest(sort_by="name", direction=SortDirection.ASC))
        )

        assert [p.name for p in page.items] == ["Alpha", "Bravo", "Charlie"]

    @pytest.mark.security
    async def test_unknown_sort_field_rejected(self, owner: Harness) -> None:
        with pytest.raises(ValidationError):
            await owner.service.list(ProjectQuery(page=PageRequest(sort_by="password_hash")))

    async def test_empty_list(self, owner: Harness) -> None:
        page = await owner.service.list(ProjectQuery())

        assert page.items == []
        assert page.total == 0
        assert page.total_pages == 1
