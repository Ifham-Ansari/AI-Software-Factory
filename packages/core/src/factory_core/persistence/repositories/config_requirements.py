"""Persistence for per-project configuration requirements.

Split from ``secrets.py`` because it is a different question: that module stores
credentials, this one records *which* credentials a project still owes. They are read
together by the configuration service and are otherwise unrelated.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from factory_core.domain.ids import ProjectId, new_id
from factory_core.persistence.models_secrets import ConfigRequirementRow


class ConfigRequirementRepository:
    """Per-project configuration requirements."""

    def __init__(self, session: AsyncSession, *, project_id: ProjectId) -> None:
        if project_id is None:
            msg = "ConfigRequirementRepository requires a project_id"  # type: ignore[unreachable]
            raise ValueError(msg)
        self._session = session
        self._project_id = project_id

    async def list_all(self) -> list[ConfigRequirementRow]:
        """Every requirement recorded for this project."""
        statement = (
            select(ConfigRequirementRow)
            .where(ConfigRequirementRow.project_id == self._project_id)
            .order_by(ConfigRequirementRow.category, ConfigRequirementRow.key)
        )
        result = await self._session.execute(statement)
        return list(result.scalars())

    async def upsert(
        self,
        key: str,
        *,
        category: str,
        description: str = "",
        required: bool = True,
    ) -> ConfigRequirementRow:
        """Record that this project needs something."""
        now = datetime.now(UTC)
        statement = select(ConfigRequirementRow).where(
            ConfigRequirementRow.project_id == self._project_id,
            ConfigRequirementRow.key == key,
        )
        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()
        if row is None:
            row = ConfigRequirementRow(
                id=new_id(),
                project_id=self._project_id,
                key=key,
                category=category,
                description=description,
                required=required,
                created_at=now,
                updated_at=now,
            )
            self._session.add(row)
        else:
            row.category = category
            row.description = description
            row.required = required
            row.updated_at = now
        await self._session.flush()
        return row

    async def mark_satisfied(self, key: str, *, satisfied: bool = True) -> bool:
        """Set satisfaction for a non-secret requirement.

        Secret-backed requirements do not use this — their satisfaction is derived from
        whether the secret exists, so storing it here would be a second truth to drift.
        """
        statement = select(ConfigRequirementRow).where(
            ConfigRequirementRow.project_id == self._project_id,
            ConfigRequirementRow.key == key,
        )
        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()
        if row is None:
            return False
        row.satisfied_at = datetime.now(UTC) if satisfied else None
        row.updated_at = datetime.now(UTC)
        await self._session.flush()
        return True
