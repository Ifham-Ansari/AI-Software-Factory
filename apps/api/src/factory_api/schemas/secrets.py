"""Secret vault and configuration request/response bodies.

**No model in this module has a field for a secret value on the response side.** That is
the "write-only API" guarantee expressed structurally: an endpoint cannot return a
plaintext credential because there is nowhere to put one. A future change that tried would
have to add a field here, which is a visible, reviewable diff.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from factory_core.application.secrets.schemas import MAX_SECRET_VALUE_LENGTH, SecretView
from factory_core.domain.config_requirements import ConfigurationReport


class StoreSecretRequest(BaseModel):
    """Write a secret value. The only place a plaintext value enters the system."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "name": "GITHUB_TOKEN",
                "value": "ghp_example_token_value",
                "description": "Push access for generated repositories.",
            }
        },
    )

    name: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Z][A-Z0-9_]{0,63}$",
        description="Environment-variable shaped: uppercase, digits, underscores.",
    )
    value: str = Field(
        min_length=1,
        max_length=MAX_SECRET_VALUE_LENGTH,
        description="The credential. Encrypted immediately and never returned.",
    )
    description: str = Field(default="", max_length=500)


class SecretResponse(BaseModel):
    """A secret's metadata. Deliberately has no value field."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    is_set: bool
    version: int
    created_at: datetime
    updated_at: datetime
    last_accessed_at: datetime | None
    reference: str = Field(description="The secret:// reference handed to agents. Safe to display.")

    @classmethod
    def from_view(cls, view: SecretView) -> SecretResponse:
        """Project the application view onto the wire representation."""
        return cls(
            name=view.name,
            description=view.description,
            is_set=view.is_set,
            version=view.version,
            created_at=view.created_at,
            updated_at=view.updated_at,
            last_accessed_at=view.last_accessed_at,
            reference=view.reference,
        )


class SecretListResponse(BaseModel):
    """Every secret a project holds."""

    model_config = ConfigDict(extra="forbid")

    items: list[SecretResponse]
    total: int


class RequirementResponse(BaseModel):
    """One configuration requirement and whether it is met."""

    model_config = ConfigDict(extra="forbid")

    key: str
    category: str
    description: str
    required: bool
    satisfied: bool
    secret_backed: bool
    help_url: str | None = None


class ConfigurationResponse(BaseModel):
    """What a project still needs before it can be built."""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    requirements: list[RequirementResponse]
    missing: list[str] = Field(
        description="Keys of required, unsatisfied entries. Empty means ready."
    )
    is_satisfied: bool

    @classmethod
    def from_report(cls, report: ConfigurationReport) -> ConfigurationResponse:
        """Project a domain report onto the wire representation."""
        return cls(
            project_id=report.project_id,
            requirements=[
                RequirementResponse(
                    key=item.key,
                    category=item.category.value,
                    description=item.description,
                    required=item.required,
                    satisfied=item.satisfied,
                    secret_backed=item.secret_backed,
                    help_url=item.help_url,
                )
                for item in report.requirements
            ],
            missing=[item.key for item in report.missing],
            is_satisfied=report.is_satisfied,
        )


class AddRequirementRequest(BaseModel):
    """Record that a project needs a catalog entry."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=64)
    required: bool = True
