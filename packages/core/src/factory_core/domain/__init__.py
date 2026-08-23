"""Domain layer: entities, value objects, policies.

This package depends on nothing else in the system. No SQLAlchemy, no FastAPI, no
LangGraph, no infrastructure. If something here needs a database, it belongs in the
application layer instead.
"""

from factory_core.domain.audit import (
    ActorType,
    AuditAction,
    AuditEntry,
    AuditRequest,
    ResourceType,
)
from factory_core.domain.entities import Project, ProjectStatus, User, UserStatus
from factory_core.domain.ids import (
    AuditEntryId,
    ProjectId,
    TokenFamilyId,
    TokenId,
    UserId,
    new_id,
    new_project_id,
    new_token_family_id,
    new_token_id,
    new_user_id,
    parse_uuid,
)
from factory_core.domain.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    Page,
    PageRequest,
    SortDirection,
)
from factory_core.domain.policies import (
    can_access_project,
    ensure_active_user,
    ensure_can_access_project,
    ensure_can_modify_project,
)
from factory_core.domain.values import (
    Email,
    Password,
    ProjectDescription,
    ProjectName,
    normalise_email,
    slugify,
)

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "ActorType",
    "AuditAction",
    "AuditEntry",
    "AuditEntryId",
    "AuditRequest",
    "Email",
    "Page",
    "PageRequest",
    "Password",
    "Project",
    "ProjectDescription",
    "ProjectId",
    "ProjectName",
    "ProjectStatus",
    "ResourceType",
    "SortDirection",
    "TokenFamilyId",
    "TokenId",
    "User",
    "UserId",
    "UserStatus",
    "can_access_project",
    "ensure_active_user",
    "ensure_can_access_project",
    "ensure_can_modify_project",
    "new_id",
    "new_project_id",
    "new_token_family_id",
    "new_token_id",
    "new_user_id",
    "normalise_email",
    "parse_uuid",
    "slugify",
]
