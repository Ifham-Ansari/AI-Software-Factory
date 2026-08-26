"""In-memory project repository for tests.

Mirrors ``ProjectRepository``, including its owner scoping: the fake refuses to be
constructed without an owner and filters every read by it, so a test that accidentally
drops scoping fails here the same way it would against SQL.

That said — a fake proves the *service* respects scoping. Only the integration suite
proves the generated SQL does. Both are required; see ``tests/integration/test_isolation``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from factory_core.domain.entities import Project, ProjectStatus
from factory_core.domain.ids import ProjectId, UserId
from factory_core.domain.pagination import Page, PageRequest, SortDirection
from factory_core.errors import AlreadyExistsError

SORTABLE_FIELDS = ("name", "created_at", "updated_at", "status")
DEFAULT_SORT = "created_at"


class FakeProjectStore:
    """Shared storage behind per-owner fake repositories.

    Separate from the repository so two repositories scoped to different owners can see
    the same underlying data — which is exactly the setup an isolation test needs.
    """

    def __init__(self) -> None:
        self.projects: dict[ProjectId, Project] = {}

    def add(self, project: Project) -> None:
        """Insert a project directly, bypassing scoping. Test setup only."""
        self.projects[project.id] = project


class FakeProjectRepository:
    """In-memory project storage scoped to one owner."""

    def __init__(self, store: FakeProjectStore, *, owner_id: UserId) -> None:
        if owner_id is None:
            # Unreachable per the annotation, kept for untyped callers — same guard, and
            # same reasoning, as the real ScopedRepository.
            msg = "FakeProjectRepository requires an owner_id"  # type: ignore[unreachable]
            raise ValueError(msg)
        self._store = store
        self._owner_id = owner_id

    @property
    def owner_id(self) -> UserId:
        """The owner this repository is scoped to."""
        return self._owner_id

    async def get(self, project_id: ProjectId) -> Project | None:
        """Load one of this owner's projects, or ``None``."""
        project = self._store.projects.get(project_id)
        return project if project and project.owner_id == self._owner_id else None

    async def slug_exists(self, slug: str, *, exclude: ProjectId | None = None) -> bool:
        """Whether this owner already uses the given slug."""
        return any(
            p.slug == slug and p.owner_id == self._owner_id and p.id != exclude
            for p in self._store.projects.values()
        )

    async def list(
        self,
        request: PageRequest,
        *,
        status: ProjectStatus | None = None,
        search: str | None = None,
    ) -> Page[Project]:
        """List this owner's projects."""
        owned = [p for p in self._store.projects.values() if p.owner_id == self._owner_id]
        if status is not None:
            owned = [p for p in owned if p.status is status]
        if search:
            needle = search.lower()
            owned = [p for p in owned if needle in p.name.lower()]

        sort_field = request.resolve_sort(SORTABLE_FIELDS, DEFAULT_SORT)
        owned.sort(
            key=lambda p: (getattr(p, sort_field), str(p.id)),
            reverse=request.direction is SortDirection.DESC,
        )
        window = owned[request.offset : request.offset + request.limit]
        return Page(
            items=window,
            total=len(owned),
            page=request.page,
            page_size=request.page_size,
        )

    async def create(
        self,
        *,
        project_id: ProjectId,
        name: str,
        slug: str,
        description: str,
        now: datetime | None = None,
    ) -> Project:
        """Insert a project owned by this repository's owner.

        Raises:
            AlreadyExistsError: The slug is taken for this owner, matching the unique
                constraint the real repository relies on.
        """
        if await self.slug_exists(slug):
            raise AlreadyExistsError("You already have a project with that name.")
        timestamp = now or datetime.now(UTC)
        project = Project(
            id=project_id,
            owner_id=self._owner_id,
            name=name,
            slug=slug,
            description=description,
            status=ProjectStatus.DRAFT,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._store.projects[project_id] = project
        return project

    async def update(
        self,
        project_id: ProjectId,
        *,
        name: str | None = None,
        slug: str | None = None,
        description: str | None = None,
    ) -> Project | None:
        """Apply a partial update to one of this owner's projects."""
        existing = await self.get(project_id)
        if existing is None:
            return None
        changes: dict[str, object] = {"updated_at": datetime.now(UTC)}
        if name is not None:
            changes["name"] = name
        if slug is not None:
            changes["slug"] = slug
        if description is not None:
            changes["description"] = description
        updated = existing.model_copy(update=changes)
        self._store.projects[project_id] = updated
        return updated

    async def archive(
        self, project_id: ProjectId, *, now: datetime | None = None
    ) -> Project | None:
        """Archive one of this owner's projects."""
        existing = await self.get(project_id)
        if existing is None:
            return None
        timestamp = now or datetime.now(UTC)
        archived = existing.model_copy(
            update={
                "status": ProjectStatus.ARCHIVED,
                "archived_at": timestamp,
                "updated_at": timestamp,
            }
        )
        self._store.projects[project_id] = archived
        return archived

    async def restore(
        self, project_id: ProjectId, *, now: datetime | None = None
    ) -> Project | None:
        """Take one of this owner's projects out of the archive."""
        existing = await self.get(project_id)
        if existing is None:
            return None
        timestamp = now or datetime.now(UTC)
        restored = existing.model_copy(
            update={
                "status": ProjectStatus.DRAFT,
                "archived_at": None,
                "updated_at": timestamp,
            }
        )
        self._store.projects[project_id] = restored
        return restored

    async def delete(self, project_id: ProjectId) -> bool:
        """Delete one of this owner's projects."""
        if await self.get(project_id) is None:
            return False
        del self._store.projects[project_id]
        return True
