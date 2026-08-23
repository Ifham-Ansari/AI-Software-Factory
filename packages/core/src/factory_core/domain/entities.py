"""Domain entities.

These are the language the application layer speaks. They are deliberately separate from
both the SQLAlchemy models (persistence detail) and the API schemas (transport detail),
so a change to a database column or a JSON field name cannot ripple through business
logic.

Entities never carry secret material. ``User`` has no password hash: hashes belong to the
persistence layer and the authentication service, and an entity that cannot hold one can
never leak one through a log line or an API response.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from factory_core.domain.ids import ProjectId, UserId
from factory_core.domain.values import Email, ProjectDescription, ProjectName


class UserStatus(StrEnum):
    """Lifecycle state of an account."""

    ACTIVE = "active"
    SUSPENDED = "suspended"

    @property
    def can_authenticate(self) -> bool:
        """Whether an account in this state may sign in."""
        return self is UserStatus.ACTIVE


class ProjectStatus(StrEnum):
    """Lifecycle state of a project.

    Phase 1 covers creation and archival only. Later phases add the states that describe
    an active build (specifying, building, deployed); they are not modelled yet because
    nothing can reach them.
    """

    DRAFT = "draft"
    ARCHIVED = "archived"


class Entity(BaseModel):
    """Base for domain entities.

    Frozen because entities are values in transit between layers: mutating one in place
    would make it unclear which copy is authoritative. State changes go through the
    application service, which persists them and returns a fresh entity.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class User(Entity):
    """A person who can sign in and own projects."""

    id: UserId
    email: Email
    display_name: str = Field(min_length=1, max_length=120)
    status: UserStatus
    created_at: datetime
    updated_at: datetime
    # None until the address is proven. A timestamp rather than a boolean because *when*
    # an address was verified is a question support and compliance actually ask.
    email_verified_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        """Whether this account may currently authenticate."""
        return self.status.can_authenticate

    @property
    def is_email_verified(self) -> bool:
        """Whether this account has proven ownership of its email address."""
        return self.email_verified_at is not None


class Project(Entity):
    """A software project owned by exactly one user.

    ``owner_id`` is the isolation boundary for the whole system. Every query that touches
    a project must be scoped by it; see ``factory_core.domain.policies``.
    """

    id: ProjectId
    owner_id: UserId
    name: ProjectName
    slug: str
    description: ProjectDescription = ""
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None

    @property
    def is_archived(self) -> bool:
        """Whether this project has been archived."""
        return self.status is ProjectStatus.ARCHIVED
