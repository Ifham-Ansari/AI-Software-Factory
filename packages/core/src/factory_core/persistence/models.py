"""SQLAlchemy ORM models.

These describe storage, not the domain. Mapping between the two happens in ``mappers.py``
so that a column rename cannot ripple into business logic, and so that storage-only
columns — password hashes, token digests — have no path into a domain entity.

All four Phase 1 tables live in one module because they are small and mutually
referential; splitting them would mean four files of a dozen lines each plus import
juggling for the foreign keys.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from factory_core.persistence.base import Base, TimestampMixin, uuid_pk

# JSONB on PostgreSQL, plain JSON elsewhere, so model definitions stay importable
# without a live Postgres dialect (needed for offline schema inspection and tooling).
JsonDict = JSON().with_variant(JSONB(), "postgresql")


class UserRow(Base, TimestampMixin):
    """A registered account.

    ``password_hash`` exists only here. It is never mapped onto a domain entity and never
    leaves the persistence and authentication layers.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    __table_args__ = (
        # Email is normalised to lowercase by the domain layer before it reaches here,
        # so a plain unique index is sufficient and avoids requiring the citext extension.
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint("status IN ('active', 'suspended')", name="status_valid"),
    )


class RefreshTokenRow(Base):
    """One issued refresh token.

    Stores the SHA-256 digest, never the token. ``family_id`` groups every token derived
    from a single sign-in, which is what makes reuse detection able to revoke a whole
    compromised session chain at once.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    family_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    issued_at: Mapped[datetime] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    __table_args__ = (
        # Lookup on presentation is by digest, and it must be unique so a digest
        # collision cannot authenticate the wrong session.
        UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        Index("ix_refresh_tokens_family_id", "family_id"),
        Index("ix_refresh_tokens_user_id", "user_id"),
        CheckConstraint("status IN ('active', 'rotated', 'revoked')", name="status_valid"),
    )


class ProjectRow(Base, TimestampMixin):
    """A software project owned by exactly one user."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        # Slugs are unique per owner, not globally: one user naming a project
        # "Inventory" must not stop anyone else from doing the same.
        UniqueConstraint("owner_id", "slug", name="uq_projects_owner_id_slug"),
        # Every project listing is "this owner's projects, newest first".
        Index("ix_projects_owner_id_created_at", "owner_id", "created_at"),
        CheckConstraint("status IN ('draft', 'archived')", name="status_valid"),
    )


class AuditLogRow(Base):
    """An append-only record of a state change or security-relevant event.

    Has no ``updated_at`` and no foreign keys to the resources it references: audit rows
    must survive deletion of the thing they describe, which is precisely when they matter
    most.
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = uuid_pk()
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audit_metadata: Mapped[dict[str, Any]] = mapped_column(JsonDict, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        Index("ix_audit_log_actor_id_created_at", "actor_id", "created_at"),
        Index("ix_audit_log_project_id_created_at", "project_id", "created_at"),
        Index("ix_audit_log_action_created_at", "action", "created_at"),
    )
