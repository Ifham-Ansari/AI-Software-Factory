"""Dependency injection providers."""

from factory_api.dependencies.auth import (
    CurrentUser,
    CurrentUserId,
    get_current_user,
    get_current_user_id,
)
from factory_api.dependencies.context import (
    RequestIdDep,
    SessionDep,
    StateDep,
    get_session,
    get_state,
)
from factory_api.dependencies.pagination import PageRequestDep
from factory_api.dependencies.repositories import (
    AuditRepositoryDep,
    RefreshTokenRepositoryDep,
    UserRepositoryDep,
    get_audit_repository,
    get_refresh_token_repository,
    get_user_repository,
)
from factory_api.dependencies.services import (
    AuthServiceDep,
    ProjectRepositoryDep,
    ProjectServiceDep,
    get_project_repository,
)

__all__ = [
    "AuditRepositoryDep",
    "AuthServiceDep",
    "CurrentUser",
    "CurrentUserId",
    "PageRequestDep",
    "ProjectRepositoryDep",
    "ProjectServiceDep",
    "RefreshTokenRepositoryDep",
    "RequestIdDep",
    "SessionDep",
    "StateDep",
    "UserRepositoryDep",
    "get_audit_repository",
    "get_current_user",
    "get_current_user_id",
    "get_project_repository",
    "get_refresh_token_repository",
    "get_session",
    "get_state",
    "get_user_repository",
]
