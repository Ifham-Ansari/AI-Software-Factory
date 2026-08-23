"""Translation between ORM rows and domain entities.

Keeping this explicit — rather than mapping the domain classes directly onto tables — is
what lets ``UserRow`` carry a password hash while ``User`` cannot. The mapping is the
enforcement point: there is simply no code path that copies a hash into an entity.
"""

from __future__ import annotations

from factory_core.domain.audit import ActorType, AuditAction, AuditEntry, ResourceType
from factory_core.domain.entities import Project, ProjectStatus, User, UserStatus
from factory_core.domain.ids import (
    AuditEntryId,
    ProjectId,
    TokenFamilyId,
    TokenId,
    UserId,
)
from factory_core.persistence.models import (
    AuditLogRow,
    ProjectRow,
    RefreshTokenRow,
    UserRow,
)
from factory_core.security.refresh import RefreshTokenRecord, RefreshTokenStatus


def to_user(row: UserRow) -> User:
    """Map a user row onto a domain entity, dropping the password hash."""
    return User(
        id=UserId(row.id),
        email=row.email,
        display_name=row.display_name,
        status=UserStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def to_project(row: ProjectRow) -> Project:
    """Map a project row onto a domain entity."""
    return Project(
        id=ProjectId(row.id),
        owner_id=UserId(row.owner_id),
        name=row.name,
        slug=row.slug,
        description=row.description,
        status=ProjectStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        archived_at=row.archived_at,
    )


def to_refresh_token(row: RefreshTokenRow) -> RefreshTokenRecord:
    """Map a refresh-token row onto its record."""
    return RefreshTokenRecord(
        id=TokenId(row.id),
        family_id=TokenFamilyId(row.family_id),
        user_id=UserId(row.user_id),
        token_hash=row.token_hash,
        status=RefreshTokenStatus(row.status),
        issued_at=row.issued_at,
        expires_at=row.expires_at,
        rotated_at=row.rotated_at,
        revoked_at=row.revoked_at,
        replaced_by_id=TokenId(row.replaced_by_id) if row.replaced_by_id else None,
    )


def to_refresh_token_row(record: RefreshTokenRecord) -> RefreshTokenRow:
    """Build a persistable row from a freshly generated refresh-token record."""
    return RefreshTokenRow(
        id=record.id,
        family_id=record.family_id,
        user_id=record.user_id,
        token_hash=record.token_hash,
        status=record.status.value,
        issued_at=record.issued_at,
        expires_at=record.expires_at,
        rotated_at=record.rotated_at,
        revoked_at=record.revoked_at,
        replaced_by_id=record.replaced_by_id,
    )


def to_audit_entry(row: AuditLogRow) -> AuditEntry:
    """Map an audit row onto a domain entity."""
    return AuditEntry(
        id=AuditEntryId(row.id),
        actor_type=ActorType(row.actor_type),
        actor_id=row.actor_id,
        action=AuditAction(row.action),
        resource_type=ResourceType(row.resource_type) if row.resource_type else None,
        resource_id=row.resource_id,
        project_id=ProjectId(row.project_id) if row.project_id else None,
        request_id=row.request_id,
        metadata=row.audit_metadata,
        created_at=row.created_at,
    )
