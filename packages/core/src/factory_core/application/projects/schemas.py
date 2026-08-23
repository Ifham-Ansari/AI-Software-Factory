"""Project commands and queries."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from factory_core.domain.entities import ProjectStatus
from factory_core.domain.pagination import PageRequest
from factory_core.domain.values import (
    MAX_DESCRIPTION_LENGTH,
    MAX_PROJECT_NAME_LENGTH,
)


class CreateProjectCommand(BaseModel):
    """Create a project."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_PROJECT_NAME_LENGTH)
    description: str = Field(default="", max_length=MAX_DESCRIPTION_LENGTH)

    @field_validator("name", "description")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("name")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        """A name of only whitespace passes ``min_length`` but is not a name."""
        if not value:
            msg = "Project name must not be blank"
            raise ValueError(msg)
        return value


class UpdateProjectCommand(BaseModel):
    """Partially update a project.

    Every field is optional and ``None`` means "leave unchanged", which is what makes this
    a PATCH rather than a PUT. An explicit empty string still clears the description.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=MAX_PROJECT_NAME_LENGTH)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)

    @field_validator("name", "description")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("name")
    @classmethod
    def _reject_blank(cls, value: str | None) -> str | None:
        if value is not None and not value:
            msg = "Project name must not be blank"
            raise ValueError(msg)
        return value

    def has_changes(self) -> bool:
        """Whether this command would change anything."""
        return self.name is not None or self.description is not None


class ProjectQuery(BaseModel):
    """Filters for listing projects."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page: PageRequest = Field(default_factory=PageRequest)
    status: ProjectStatus | None = None
    search: str | None = Field(default=None, max_length=120)

    @field_validator("search")
    @classmethod
    def _normalise_search(cls, value: str | None) -> str | None:
        """Treat a blank search as no search rather than as a match-everything filter."""
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None
