"""Project persistence, scoped to a single owner."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Select, select

from factory_core.domain.entities import Project, ProjectStatus
from factory_core.domain.ids import ProjectId
from factory_core.domain.pagination import Page, PageRequest, SortDirection
from factory_core.persistence.mappers import to_project
from factory_core.persistence.models import ProjectRow
from factory_core.persistence.repositories.base import ScopedRepository

SORTABLE_FIELDS = ("name", "created_at", "updated_at", "status")
DEFAULT_SORT = "created_at"


class ProjectRepository(ScopedRepository):
    """Reads and writes projects for exactly one owner.

    Every statement below applies ``self.scope(...)``. A method that omits it would
    return another user's projects, so ``tests/integration/test_isolation.py`` exercises
    each read path with a second user's identifier.
    """

    async def get(self, project_id: ProjectId) -> Project | None:
        """Load one of this owner's projects.

        Returns ``None`` both when the project does not exist and when it belongs to
        someone else. The caller cannot distinguish the two, which is what stops the
        endpoint being used to enumerate other users' projects.
        """
        statement = select(ProjectRow).where(
            ProjectRow.id == project_id,
            self.scope(ProjectRow.owner_id),
        )
        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()
        return to_project(row) if row else None

    async def slug_exists(self, slug: str, *, exclude: ProjectId | None = None) -> bool:
        """Whether this owner already has a project with the given slug."""
        statement = select(ProjectRow.id).where(
            ProjectRow.slug == slug,
            self.scope(ProjectRow.owner_id),
        )
        if exclude is not None:
            statement = statement.where(ProjectRow.id != exclude)
        result = await self._session.execute(statement.limit(1))
        return result.first() is not None

    async def list(
        self,
        request: PageRequest,
        *,
        status: ProjectStatus | None = None,
        search: str | None = None,
    ) -> Page[Project]:
        """List this owner's projects.

        Args:
            request: Pagination and sorting. The sort field is validated against
                ``SORTABLE_FIELDS`` rather than interpolated.
            status: Optional status filter.
            search: Optional case-insensitive substring match on the name.
        """
        statement = self._filtered(status=status, search=search)
        total = await self._count(statement)
        if total == 0:
            return Page.empty(request)

        sort_field = request.resolve_sort(SORTABLE_FIELDS, DEFAULT_SORT)
        column = getattr(ProjectRow, sort_field)
        ordering = column.desc() if request.direction is SortDirection.DESC else column.asc()

        # Tie-break on the primary key so that rows with identical sort values keep a
        # stable order across pages. Without it, paging can show or skip a row.
        page_statement = (
            statement.order_by(ordering, ProjectRow.id.asc())
            .offset(request.offset)
            .limit(request.limit)
        )
        result = await self._session.execute(page_statement)
        items = [to_project(row) for row in result.scalars().all()]
        return Page(items=items, total=total, page=request.page, page_size=request.page_size)

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

        Ownership is taken from the repository scope, never from a caller argument, so a
        request body cannot assign a project to a different user.
        """
        timestamp = now or datetime.now(UTC)
        row = ProjectRow(
            id=project_id,
            owner_id=self.owner_id,
            name=name,
            slug=slug,
            description=description,
            status=ProjectStatus.DRAFT.value,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._session.add(row)
        await self._session.flush()
        return to_project(row)

    async def update(
        self,
        project_id: ProjectId,
        *,
        name: str | None = None,
        slug: str | None = None,
        description: str | None = None,
        now: datetime | None = None,
    ) -> Project | None:
        """Apply a partial update to one of this owner's projects."""
        row = await self._scoped_row(project_id)
        if row is None:
            return None
        if name is not None:
            row.name = name
        if slug is not None:
            row.slug = slug
        if description is not None:
            row.description = description
        row.updated_at = now or datetime.now(UTC)
        await self._session.flush()
        return to_project(row)

    async def archive(
        self, project_id: ProjectId, *, now: datetime | None = None
    ) -> Project | None:
        """Archive a project. Archived projects are read-only, not deleted."""
        row = await self._scoped_row(project_id)
        if row is None:
            return None
        timestamp = now or datetime.now(UTC)
        row.status = ProjectStatus.ARCHIVED.value
        row.archived_at = timestamp
        row.updated_at = timestamp
        await self._session.flush()
        return to_project(row)

    async def delete(self, project_id: ProjectId) -> bool:
        """Permanently delete a project.

        Returns:
            Whether a row was deleted.
        """
        row = await self._scoped_row(project_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True

    def _filtered(
        self, *, status: ProjectStatus | None, search: str | None
    ) -> Select[tuple[ProjectRow]]:
        statement = select(ProjectRow).where(self.scope(ProjectRow.owner_id))
        if status is not None:
            statement = statement.where(ProjectRow.status == status.value)
        if search:
            # ilike with escaped wildcards: a user searching for "100%" must not match
            # everything.
            pattern = f"%{search.replace('%', r'\%').replace('_', r'\_')}%"
            statement = statement.where(ProjectRow.name.ilike(pattern, escape="\\"))
        return statement

    async def _scoped_row(self, project_id: ProjectId) -> ProjectRow | None:
        statement = select(ProjectRow).where(
            ProjectRow.id == project_id,
            self.scope(ProjectRow.owner_id),
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()
