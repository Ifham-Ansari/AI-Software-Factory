"""Audit trail.

Every action that changes state, and every security-relevant action that fails, writes
one of these. The audit log is append-only: rows are never updated or deleted, because a
tamper-evident history is the point.

``metadata`` must never contain secret material. It passes through the same redactor as
logs on the way in, but the primary defence is not putting it there.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from factory_core.domain.ids import AuditEntryId, ProjectId, UserId


class ActorType(StrEnum):
    """What kind of principal performed an action."""

    USER = "user"
    SYSTEM = "system"
    AGENT = "agent"


class AuditAction(StrEnum):
    """Auditable actions.

    Values are stable strings stored in the database and queried by operators. Add new
    ones; never rename an existing one.
    """

    # Identity
    USER_REGISTERED = "user.registered"
    USER_SIGNED_IN = "user.signed_in"
    USER_SIGN_IN_FAILED = "user.sign_in_failed"
    USER_SIGNED_OUT = "user.signed_out"

    # Email verification
    VERIFICATION_SENT = "verification.sent"
    VERIFICATION_SUCCEEDED = "verification.succeeded"
    VERIFICATION_FAILED = "verification.failed"
    VERIFICATION_EXHAUSTED = "verification.exhausted"

    # Tokens
    TOKEN_REFRESHED = "token.refreshed"
    TOKEN_REUSE_DETECTED = "token.reuse_detected"
    TOKEN_FAMILY_REVOKED = "token.family_revoked"

    # Projects
    PROJECT_CREATED = "project.created"
    PROJECT_UPDATED = "project.updated"
    PROJECT_ARCHIVED = "project.archived"
    PROJECT_DELETED = "project.deleted"

    # Authorization
    ACCESS_DENIED = "access.denied"


class ResourceType(StrEnum):
    """The kind of resource an audited action targeted."""

    USER = "user"
    PROJECT = "project"
    TOKEN = "token"


class AuditEntry(BaseModel):
    """One immutable record of something that happened."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: AuditEntryId
    actor_type: ActorType
    actor_id: str | None
    action: AuditAction
    resource_type: ResourceType | None
    resource_id: str | None
    project_id: ProjectId | None
    request_id: str | None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AuditRequest(BaseModel):
    """A request to record an audit entry.

    Separate from ``AuditEntry`` because the caller supplies intent while the writer
    supplies identity and time. A caller cannot forge a timestamp or an entry id.
    """

    model_config = ConfigDict(extra="forbid")

    actor_type: ActorType = ActorType.USER
    actor_id: str | None = None
    action: AuditAction
    resource_type: ResourceType | None = None
    resource_id: str | None = None
    project_id: ProjectId | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def for_user(
        cls,
        action: AuditAction,
        user_id: UserId | None,
        **metadata: Any,
    ) -> AuditRequest:
        """Build a request describing a user acting on themselves."""
        return cls(
            actor_type=ActorType.USER,
            actor_id=str(user_id) if user_id else None,
            action=action,
            resource_type=ResourceType.USER,
            resource_id=str(user_id) if user_id else None,
            metadata=metadata,
        )

    @classmethod
    def for_project(
        cls,
        action: AuditAction,
        user_id: UserId,
        project_id: ProjectId,
        **metadata: Any,
    ) -> AuditRequest:
        """Build a request describing a user acting on one of their projects."""
        return cls(
            actor_type=ActorType.USER,
            actor_id=str(user_id),
            action=action,
            resource_type=ResourceType.PROJECT,
            resource_id=str(project_id),
            project_id=project_id,
            metadata=metadata,
        )
