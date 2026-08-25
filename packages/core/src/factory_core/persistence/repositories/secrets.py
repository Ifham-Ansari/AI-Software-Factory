"""Persistence for the secret vault.

Three repositories, one concern. All of them are **scoped by project**, and none returns a
plaintext value — decryption happens a layer up, in the vault service, which is the only
place that holds key material.

``SecretRepository.get_ciphertext`` deliberately returns raw bytes rather than a decrypted
string. Keeping decryption out of persistence means a future query, migration script, or
admin tool that reaches for a repository cannot accidentally produce plaintext.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from factory_core.domain.ids import ProjectId, new_id, new_secret_id
from factory_core.persistence.models_secrets import (
    ProjectKeyRow,
    SecretAccessLogRow,
    SecretRow,
)


class ProjectKeyRepository:
    """The wrapped data encryption key for each project."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, project_id: ProjectId) -> ProjectKeyRow | None:
        """Fetch a project's key row, or ``None`` if it has none yet."""
        statement = select(ProjectKeyRow).where(ProjectKeyRow.project_id == project_id)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def create(
        self, project_id: ProjectId, *, wrapped_dek: str, key_version: str
    ) -> ProjectKeyRow:
        """Store a newly generated wrapped DEK."""
        now = datetime.now(UTC)
        row = ProjectKeyRow(
            id=new_id(),
            project_id=project_id,
            wrapped_dek=wrapped_dek,
            key_version=key_version,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def update_wrapping(
        self, project_id: ProjectId, *, wrapped_dek: str, key_version: str
    ) -> bool:
        """Replace the wrapping after a KEK rotation. The DEK itself is unchanged."""
        row = await self.get(project_id)
        if row is None:
            return False
        now = datetime.now(UTC)
        row.wrapped_dek = wrapped_dek
        row.key_version = key_version
        row.rotated_at = now
        row.updated_at = now
        await self._session.flush()
        return True

    async def list_on_version(self, key_version: str, *, limit: int = 100) -> list[ProjectKeyRow]:
        """Find keys still wrapped with a given KEK version.

        Drives the rotation sweep: anything returned still needs re-wrapping before that
        version can be dropped from configuration.
        """
        statement = (
            select(ProjectKeyRow).where(ProjectKeyRow.key_version == key_version).limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars())


class SecretRepository:
    """Encrypted project credentials.

    Scoped to one project by construction, mirroring ``ScopedRepository``'s contract for
    owner-scoped data: there is no method that can read across projects.
    """

    def __init__(self, session: AsyncSession, *, project_id: ProjectId) -> None:
        """Bind to one project.

        Raises:
            ValueError: No project id. An unscoped secret repository would be able to
                read every project's credentials.
        """
        if project_id is None:
            msg = "SecretRepository requires a project_id"  # type: ignore[unreachable]
            raise ValueError(msg)
        self._session = session
        self._project_id = project_id

    @property
    def project_id(self) -> ProjectId:
        """The project this repository is bound to."""
        return self._project_id

    async def get(self, name: str) -> SecretRow | None:
        """Fetch one secret's row, ciphertext included, plaintext not."""
        statement = select(SecretRow).where(
            SecretRow.project_id == self._project_id, SecretRow.name == name
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_names(self) -> list[SecretRow]:
        """Every secret this project holds, newest first.

        Returns rows because callers need metadata — name, description, timestamps. The
        ciphertext travels with them and is discarded by the schema that renders them.
        """
        statement = (
            select(SecretRow)
            .where(SecretRow.project_id == self._project_id)
            .order_by(SecretRow.name)
        )
        result = await self._session.execute(statement)
        return list(result.scalars())

    async def upsert(
        self, name: str, *, ciphertext: bytes, key_version: str, description: str = ""
    ) -> SecretRow:
        """Create or replace a secret's value.

        Replacing bumps ``version`` so an audit reader can tell that a credential was
        rotated rather than merely re-read.
        """
        now = datetime.now(UTC)
        row = await self.get(name)
        if row is None:
            row = SecretRow(
                id=new_secret_id(),
                project_id=self._project_id,
                name=name,
                ciphertext=ciphertext,
                description=description,
                key_version=key_version,
                version=1,
                created_at=now,
                updated_at=now,
            )
            self._session.add(row)
        else:
            row.ciphertext = ciphertext
            row.key_version = key_version
            row.version += 1
            row.updated_at = now
            if description:
                row.description = description
        await self._session.flush()
        return row

    async def delete(self, name: str) -> bool:
        """Remove a secret. Returns whether one existed."""
        row = await self.get(name)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True

    async def mark_accessed(self, name: str, *, now: datetime | None = None) -> None:
        """Record that a value was resolved, for the vault UI's "last used" column."""
        row = await self.get(name)
        if row is not None:
            row.last_accessed_at = now or datetime.now(UTC)

    async def existing_names(self) -> set[str]:
        """The set of secret names present, for deriving requirement satisfaction."""
        statement = select(SecretRow.name).where(SecretRow.project_id == self._project_id)
        result = await self._session.execute(statement)
        return set(result.scalars())


class SecretAccessLogRepository:
    """Append-only record of secret resolutions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        project_id: ProjectId,
        secret_name: str,
        sink: str,
        purpose: str,
        actor_type: str,
        actor_id: str | None = None,
        run_id: uuid.UUID | None = None,
        request_id: str | None = None,
        granted: bool = True,
    ) -> None:
        """Write one access record.

        Called inside the same transaction as the resolution, so a value cannot be read
        without this row existing — including when the attempt was refused, which is the
        row an investigation actually wants.
        """
        self._session.add(
            SecretAccessLogRow(
                id=new_id(),
                project_id=project_id,
                secret_name=secret_name,
                sink=sink,
                purpose=purpose[:200],
                actor_type=actor_type,
                actor_id=actor_id,
                run_id=run_id,
                request_id=request_id,
                granted=granted,
                created_at=datetime.now(UTC),
            )
        )
        await self._session.flush()

    async def list_for_project(
        self, project_id: ProjectId, *, limit: int = 50
    ) -> list[SecretAccessLogRow]:
        """Most recent accesses for a project."""
        statement = (
            select(SecretAccessLogRow)
            .where(SecretAccessLogRow.project_id == project_id)
            .order_by(SecretAccessLogRow.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars())
