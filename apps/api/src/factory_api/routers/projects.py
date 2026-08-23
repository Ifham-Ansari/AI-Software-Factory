"""Project endpoints.

Every route here depends on ``ProjectServiceDep``, which depends on the authenticated
user. That chain is what enforces isolation: the service is handed a repository already
scoped to the caller, so no path parameter can reach another user's data.

Project ids arrive as strings and are parsed rather than declared as ``UUID`` path types.
A malformed id must return 404 like any other unknown project — a 422 would tell a caller
that their guess was at least *shaped* right, which is the first step of enumeration.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from factory_api.dependencies import PageRequestDep, ProjectServiceDep
from factory_api.schemas import (
    CreateProjectRequest,
    PageMeta,
    PaginatedResponse,
    ProjectResponse,
    UpdateProjectRequest,
)
from factory_api.schemas.errors import ErrorResponse
from factory_core.application.projects import (
    CreateProjectCommand,
    ProjectQuery,
    UpdateProjectCommand,
)
from factory_core.domain.entities import ProjectStatus
from factory_core.domain.ids import ProjectId, parse_uuid
from factory_core.errors import NotFoundError

router = APIRouter(prefix="/projects", tags=["projects"])

_AUTH_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


def _project_id(raw: str) -> ProjectId:
    """Parse a path parameter into a project id.

    Raises:
        NotFoundError: The value is not a UUID. Indistinguishable from a project that
            does not exist, on purpose.
    """
    parsed = parse_uuid(raw)
    if parsed is None:
        raise NotFoundError("The requested project was not found.")
    return ProjectId(parsed)


@router.get(
    "",
    response_model=PaginatedResponse[ProjectResponse],
    responses={401: {"model": ErrorResponse}},
    summary="List projects",
)
async def list_projects(
    service: ProjectServiceDep,
    page: PageRequestDep,
    status_filter: ProjectStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=120),
) -> PaginatedResponse[ProjectResponse]:
    """List the authenticated user's projects."""
    result = await service.list(ProjectQuery(page=page, status=status_filter, search=search))
    return PaginatedResponse(
        items=[ProjectResponse.from_entity(project) for project in result.items],
        meta=PageMeta.from_page(result),
    )


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    responses={401: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    summary="Create a project",
)
async def create_project(body: CreateProjectRequest, service: ProjectServiceDep) -> ProjectResponse:
    """Create a project owned by the authenticated user."""
    project = await service.create(
        CreateProjectCommand(name=body.name, description=body.description)
    )
    return ProjectResponse.from_entity(project)


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    responses=_AUTH_ERRORS,
    summary="Get a project",
)
async def get_project(project_id: str, service: ProjectServiceDep) -> ProjectResponse:
    """Return one of the authenticated user's projects."""
    return ProjectResponse.from_entity(await service.get(_project_id(project_id)))


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    responses={**_AUTH_ERRORS, 403: {"model": ErrorResponse}},
    summary="Update a project",
)
async def update_project(
    project_id: str, body: UpdateProjectRequest, service: ProjectServiceDep
) -> ProjectResponse:
    """Apply a partial update. Omitted fields are left unchanged."""
    project = await service.update(
        _project_id(project_id),
        UpdateProjectCommand(name=body.name, description=body.description),
    )
    return ProjectResponse.from_entity(project)


@router.post(
    "/{project_id}/archive",
    response_model=ProjectResponse,
    responses={**_AUTH_ERRORS, 403: {"model": ErrorResponse}},
    summary="Archive a project",
)
async def archive_project(project_id: str, service: ProjectServiceDep) -> ProjectResponse:
    """Archive a project, making it read-only. Archiving is not deletion."""
    return ProjectResponse.from_entity(await service.archive(_project_id(project_id)))


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_AUTH_ERRORS,
    summary="Delete a project",
)
async def delete_project(project_id: str, service: ProjectServiceDep) -> None:
    """Permanently delete a project. The audit entry outlives the row."""
    await service.delete(_project_id(project_id))
