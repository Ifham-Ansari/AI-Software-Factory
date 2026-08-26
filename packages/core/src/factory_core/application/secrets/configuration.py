"""Project configuration requirements and their satisfaction.

Answers one question: *what does this project still need before it can be built?*

Satisfaction for a secret-backed requirement is derived from whether the secret exists,
never stored. Storing it would create a second truth that drifts the moment someone
deletes a secret without updating a flag — and the flag is the one the UI would believe.

Non-secret requirements (a region, a plan tier) have nothing to derive from, so those do
carry an explicit ``satisfied_at``.
"""

from __future__ import annotations

from factory_core.domain.config_requirements import (
    CATALOG,
    ConfigurationReport,
    RequirementCategory,
    RequirementStatus,
    get_requirement,
)
from factory_core.domain.ids import ProjectId
from factory_core.persistence.repositories.config_requirements import (
    ConfigRequirementRepository,
)
from factory_core.persistence.repositories.secrets import SecretRepository


class ConfigurationService:
    """Records what a project needs and reports what it is missing."""

    def __init__(
        self,
        *,
        requirements: ConfigRequirementRepository,
        secrets: SecretRepository,
        project_id: ProjectId,
    ) -> None:
        self._requirements = requirements
        self._secrets = secrets
        self._project_id = project_id

    async def require(self, key: str, *, required: bool = True) -> bool:
        """Record that this project needs a catalog entry.

        Returns:
            Whether the key was recognised. An unknown key is ignored rather than raising
            because the caller in Phase 3 is an LLM-driven intake agent, and an
            unrecognised suggestion should be dropped, not crash the run.
        """
        spec = get_requirement(key)
        if spec is None:
            return False
        await self._requirements.upsert(
            spec.key,
            category=spec.category.value,
            description=spec.description,
            required=required,
        )
        return True

    async def require_all(self, keys: list[str]) -> list[str]:
        """Record several requirements, returning the ones that were recognised."""
        accepted: list[str] = []
        for key in keys:
            if await self.require(key):
                accepted.append(key)
        return accepted

    async def satisfy(self, key: str, *, satisfied: bool = True) -> bool:
        """Mark a non-secret requirement satisfied.

        Returns:
            ``False`` for a secret-backed key — its satisfaction is derived, and allowing
            it to be set here would let a project claim to hold a credential it does not.
        """
        spec = get_requirement(key)
        if spec is None or spec.secret_backed:
            return False
        satisfied_now: bool = await self._requirements.mark_satisfied(key, satisfied=satisfied)
        return satisfied_now

    async def report(self) -> ConfigurationReport:
        """Describe every requirement and whether it is met."""
        rows = await self._requirements.list_all()
        present = await self._secrets.existing_names()

        statuses: list[RequirementStatus] = []
        for row in rows:
            spec = CATALOG.get(row.key)
            secret_backed = spec.secret_backed if spec else True
            satisfied = row.key in present if secret_backed else row.satisfied_at is not None
            statuses.append(
                RequirementStatus(
                    key=row.key,
                    category=RequirementCategory(row.category),
                    description=row.description or (spec.description if spec else ""),
                    required=row.required,
                    satisfied=satisfied,
                    secret_backed=secret_backed,
                    help_url=spec.help_url if spec else None,
                )
            )
        return ConfigurationReport(project_id=str(self._project_id), requirements=tuple(statuses))
