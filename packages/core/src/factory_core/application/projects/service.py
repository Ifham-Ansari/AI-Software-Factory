"""Project use cases.

The service is constructed with a repository that is already scoped to the acting user,
so ownership is structural: there is no argument through which a caller could ask for
someone else's project. Policy checks then decide what an owner may do with their own
project — an archived one is read-only, for example.
"""

from __future__ import annotations

from factory_core.application.ports import Clock, SystemClock
from factory_core.application.projects.schemas import (
    CreateProjectCommand,
    ProjectQuery,
    UpdateProjectCommand,
)
from factory_core.domain.audit import AuditAction, AuditRequest
from factory_core.domain.entities import Project
from factory_core.domain.ids import ProjectId, UserId, new_project_id
from factory_core.domain.pagination import Page
from factory_core.domain.policies import (
    ensure_can_access_project,
    ensure_can_modify_project,
    ensure_can_restore_project,
)
from factory_core.domain.values import slugify
from factory_core.errors import AlreadyExistsError, ValidationError
from factory_core.observability import get_logger
from factory_core.persistence.repositories import AuditRepository, ProjectRepository

logger = get_logger(__name__)

# Bound on slug disambiguation attempts. Reaching it means a user has 50 projects whose
# names all slugify identically, which is a naming problem, not a system problem.
_MAX_SLUG_ATTEMPTS = 50


class ProjectService:
    """Creates, reads, updates and archives projects for one user."""

    def __init__(
        self,
        *,
        projects: ProjectRepository,
        audit: AuditRepository,
        actor_id: UserId,
        clock: Clock | None = None,
        request_id: str | None = None,
    ) -> None:
        self._projects = projects
        self._audit = audit
        self._actor_id = actor_id
        self._clock = clock or SystemClock()
        self._request_id = request_id

    async def create(self, command: CreateProjectCommand) -> Project:
        """Create a project owned by the acting user.

        Raises:
            AlreadyExistsError: The user already has too many projects with this name.
        """
        slug = await self._unique_slug(slugify(command.name))
        project = await self._projects.create(
            project_id=new_project_id(),
            name=command.name,
            slug=slug,
            description=command.description,
            now=self._clock.now(),
        )
        await self._record(AuditAction.PROJECT_CREATED, project.id, name=project.name)
        logger.info("project.created", project_id=str(project.id), slug=slug)
        return project

    async def get(self, project_id: ProjectId) -> Project:
        """Load one of the acting user's projects.

        Raises:
            NotFoundError: No such project, or it belongs to someone else. The two are
                deliberately indistinguishable.
        """
        return ensure_can_access_project(self._actor_id, await self._projects.get(project_id))

    async def list(self, query: ProjectQuery) -> Page[Project]:
        """List the acting user's projects."""
        return await self._projects.list(query.page, status=query.status, search=query.search)

    async def update(self, project_id: ProjectId, command: UpdateProjectCommand) -> Project:
        """Apply a partial update.

        Raises:
            ValidationError: The command would change nothing.
            NotFoundError: No such project, or it belongs to someone else.
            AuthorizationError: The project is archived and therefore read-only.
        """
        if not command.has_changes():
            raise ValidationError("No changes were supplied.")

        existing = ensure_can_modify_project(self._actor_id, await self._projects.get(project_id))

        # Renaming re-derives the slug, so links stay meaningful. Uniqueness excludes this
        # project, otherwise renaming to a variant of its own name would collide with it.
        slug = None
        if command.name is not None and command.name != existing.name:
            slug = await self._unique_slug(slugify(command.name), exclude=project_id)

        updated = await self._projects.update(
            project_id, name=command.name, slug=slug, description=command.description
        )
        if updated is None:
            # Only reachable if the row vanished between the check and the write.
            raise ValidationError("The project could not be updated.")

        changed = [f for f in ("name", "description") if getattr(command, f) is not None]
        await self._record(AuditAction.PROJECT_UPDATED, project_id, fields=changed)
        logger.info("project.updated", project_id=str(project_id), fields=changed)
        return updated

    async def archive(self, project_id: ProjectId) -> Project:
        """Archive a project, making it read-only.

        Raises:
            NotFoundError: No such project, or it belongs to someone else.
            AuthorizationError: The project is already archived.
        """
        ensure_can_modify_project(self._actor_id, await self._projects.get(project_id))

        archived = await self._projects.archive(project_id, now=self._clock.now())
        if archived is None:
            raise ValidationError("The project could not be archived.")

        await self._record(AuditAction.PROJECT_ARCHIVED, project_id)
        logger.info("project.archived", project_id=str(project_id))
        return archived

    async def restore(self, project_id: ProjectId) -> Project:
        """Take a project out of the archive.

        Raises:
            NotFoundError: No such project, or it belongs to someone else.
            ValidationError: The project is not archived, so there is nothing to restore.
        """
        ensure_can_restore_project(self._actor_id, await self._projects.get(project_id))

        restored = await self._projects.restore(project_id, now=self._clock.now())
        if restored is None:
            raise ValidationError("The project could not be restored.")

        await self._record(AuditAction.PROJECT_RESTORED, project_id)
        logger.info("project.restored", project_id=str(project_id))
        return restored

    async def delete(self, project_id: ProjectId) -> None:
        """Permanently delete a project.

        The audit entry is written before the delete so that the record of the deletion
        survives the row it describes.

        Raises:
            NotFoundError: No such project, or it belongs to someone else.
        """
        project = ensure_can_access_project(self._actor_id, await self._projects.get(project_id))
        await self._record(AuditAction.PROJECT_DELETED, project_id, name=project.name)
        await self._projects.delete(project_id)
        logger.info("project.deleted", project_id=str(project_id))

    async def _unique_slug(self, base: str, *, exclude: ProjectId | None = None) -> str:
        """Find a slug this owner is not already using.

        Slugs are unique per owner, so a collision only happens against the same user's
        own projects. Appending a counter is friendlier than rejecting the name.
        """
        if not await self._projects.slug_exists(base, exclude=exclude):
            return base
        for suffix in range(2, _MAX_SLUG_ATTEMPTS + 2):
            candidate = f"{base}-{suffix}"
            if not await self._projects.slug_exists(candidate, exclude=exclude):
                return candidate
        raise AlreadyExistsError("You already have too many projects with a similar name.")

    async def _record(self, action: AuditAction, project_id: ProjectId, **metadata: object) -> None:
        await self._audit.record(
            AuditRequest.for_project(action, self._actor_id, project_id, **metadata),
            request_id=self._request_id,
            now=self._clock.now(),
        )
