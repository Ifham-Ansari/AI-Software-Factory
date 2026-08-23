"""Project request and response bodies."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from factory_core.domain.entities import Project
from factory_core.domain.values import MAX_DESCRIPTION_LENGTH, MAX_PROJECT_NAME_LENGTH


class CreateProjectRequest(BaseModel):
    """Create a project."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "name": "Restaurant System",
                "description": "Inventory, orders and staff scheduling.",
            }
        },
    )

    name: str = Field(min_length=1, max_length=MAX_PROJECT_NAME_LENGTH)
    description: str = Field(default="", max_length=MAX_DESCRIPTION_LENGTH)


class UpdateProjectRequest(BaseModel):
    """Partially update a project.

    Omitted fields are left unchanged. An explicit empty description clears it.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=MAX_PROJECT_NAME_LENGTH)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)


class ProjectResponse(BaseModel):
    """A project, as returned to clients.

    ``owner_id`` is deliberately omitted: a caller can only ever see their own projects,
    so it carries no information and including it would invite clients to build
    ownership logic that belongs on the server.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    slug: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None

    @classmethod
    def from_entity(cls, project: Project) -> ProjectResponse:
        """Project a domain entity onto its wire representation."""
        return cls(
            id=str(project.id),
            name=project.name,
            slug=project.slug,
            description=project.description,
            status=project.status.value,
            created_at=project.created_at,
            updated_at=project.updated_at,
            archived_at=project.archived_at,
        )
