"""What a project needs before it can be built and deployed.

A requirement is a *question the platform must ask the user*: which database, which
deployment provider, which API key. Phase 3's intake agent produces them from a project
specification; Phase 2 provides the catalog and the satisfaction model so that "what is
this project still missing?" is answerable before any agent exists.

The catalog is code rather than data because each entry carries behaviour — whether it is
secret-backed, how it is validated, what it is for. A database table of requirement
*types* would be a lookup table nobody can change without a migration, and would still
need this mapping to mean anything.

Requirements are per-project rows referencing a catalog key. Satisfaction for a
secret-backed requirement is **derived** from the presence of the secret rather than
stored: two sources of truth for "is this set?" would eventually disagree, and the one
that matters is whether the value is actually there.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from factory_core.security.references import is_valid_secret_name


class RequirementCategory(StrEnum):
    """What area of the build a requirement belongs to.

    Used to group the UI prompt — asking for six unrelated credentials in one list is
    how a user abandons setup.
    """

    DATABASE = "database"
    DEPLOYMENT = "deployment"
    VERSION_CONTROL = "version_control"
    INTEGRATION = "integration"
    RUNTIME = "runtime"


@dataclass(frozen=True, slots=True)
class ConfigRequirementSpec:
    """One thing a project may need.

    Attributes:
        key: Stable identifier, also the secret name when ``secret_backed``.
        category: Grouping for presentation.
        description: Shown to the user when asking for it.
        secret_backed: Whether satisfying it means storing an encrypted value. A
            non-secret requirement is satisfied by a recorded choice instead — a region
            or a plan tier is configuration, not a credential, and encrypting it would
            make it unreadable to the code that needs to branch on it.
        help_url: Where the user can obtain the value.
    """

    key: str
    category: RequirementCategory
    description: str
    secret_backed: bool = True
    help_url: str | None = None

    def __post_init__(self) -> None:
        if self.secret_backed and not is_valid_secret_name(self.key):
            msg = f"secret-backed requirement key {self.key!r} must be a valid secret name"
            raise ValueError(msg)


#: The requirements this platform knows how to ask for.
#:
#: Deliberately small. Each entry is a credential the system genuinely needs to complete a
#: build, and adding one means committing to using it — a catalog full of aspirational
#: entries would produce a setup form that asks for things nothing reads.
CATALOG: dict[str, ConfigRequirementSpec] = {
    spec.key: spec
    for spec in (
        ConfigRequirementSpec(
            key="DATABASE_URL",
            category=RequirementCategory.DATABASE,
            description="Connection string for the generated application's database.",
            help_url="https://neon.tech/docs/connect/connect-from-any-app",
        ),
        ConfigRequirementSpec(
            key="NEON_API_KEY",
            category=RequirementCategory.DATABASE,
            description="Neon API key, used to provision a database for this project.",
            help_url="https://neon.tech/docs/manage/api-keys",
        ),
        ConfigRequirementSpec(
            key="GITHUB_TOKEN",
            category=RequirementCategory.VERSION_CONTROL,
            description="GitHub token with repository scope, for pushing generated code.",
            help_url="https://docs.github.com/en/authentication",
        ),
        ConfigRequirementSpec(
            key="VERCEL_TOKEN",
            category=RequirementCategory.DEPLOYMENT,
            description="Vercel token, used to deploy the generated frontend.",
            help_url="https://vercel.com/docs/rest-api",
        ),
        ConfigRequirementSpec(
            key="DEPLOY_REGION",
            category=RequirementCategory.DEPLOYMENT,
            description="Region to deploy into, for example iad1 or fra1.",
            # A region is a choice, not a credential: the deployment code has to read it.
            secret_backed=False,
        ),
    )
}


def get_requirement(key: str) -> ConfigRequirementSpec | None:
    """Look up a catalog entry."""
    return CATALOG.get(key)


def requirements_for(category: RequirementCategory) -> list[ConfigRequirementSpec]:
    """Every catalog entry in one category."""
    return [spec for spec in CATALOG.values() if spec.category is category]


@dataclass(frozen=True, slots=True)
class RequirementStatus:
    """A project's standing against one requirement."""

    key: str
    category: RequirementCategory
    description: str
    required: bool
    satisfied: bool
    secret_backed: bool
    help_url: str | None = None


@dataclass(frozen=True, slots=True)
class ConfigurationReport:
    """Everything a project still needs, and what it already has."""

    project_id: str
    requirements: tuple[RequirementStatus, ...]

    @property
    def missing(self) -> tuple[RequirementStatus, ...]:
        """Required entries that are not yet satisfied.

        This is the answer to "why can this project not build yet?".
        """
        return tuple(r for r in self.requirements if r.required and not r.satisfied)

    @property
    def is_satisfied(self) -> bool:
        """Whether every required entry is present."""
        return not self.missing
