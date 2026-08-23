"""Service construction.

Services are built per request because two of their collaborators are request-scoped: the
session (one transaction per request) and the acting user's identity.

``get_project_service`` is where project isolation is established. The repository is
constructed with the authenticated user's id, so every query the service can possibly
issue is already scoped. No route argument can widen it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from factory_api.dependencies.auth import CurrentUserId
from factory_api.dependencies.context import RequestIdDep, SessionDep, StateDep
from factory_api.dependencies.repositories import (
    AuditRepositoryDep,
    RefreshTokenRepositoryDep,
    UserRepositoryDep,
)
from factory_core.application.auth import AuthService
from factory_core.application.projects import ProjectService
from factory_core.persistence import ProjectRepository


def get_project_repository(session: SessionDep, actor_id: CurrentUserId) -> ProjectRepository:
    """Provide a project repository scoped to the authenticated user.

    The scope comes from the verified access token, never from a request body or path
    parameter, so there is no input a caller can craft to widen it.
    """
    return ProjectRepository(session, owner_id=actor_id)


ProjectRepositoryDep = Annotated[ProjectRepository, Depends(get_project_repository)]


def get_auth_service(
    state: StateDep,
    users: UserRepositoryDep,
    tokens: RefreshTokenRepositoryDep,
    audit: AuditRepositoryDep,
    request_id: RequestIdDep,
) -> AuthService:
    """Build the authentication service for this request."""
    return AuthService(
        users=users,
        tokens=tokens,
        audit=audit,
        hasher=state.hasher,
        issuer=state.issuer,
        refresh_ttl_seconds=state.settings.security.refresh_token_ttl_seconds,
        request_id=request_id,
    )


def get_project_service(
    projects: ProjectRepositoryDep,
    audit: AuditRepositoryDep,
    actor_id: CurrentUserId,
    request_id: RequestIdDep,
) -> ProjectService:
    """Build the project service, scoped to the authenticated user.

    Depending on ``CurrentUserId`` means a route using this service is authenticated by
    construction: an unauthenticated request never reaches the handler.
    """
    return ProjectService(
        projects=projects,
        audit=audit,
        actor_id=actor_id,
        request_id=request_id,
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
