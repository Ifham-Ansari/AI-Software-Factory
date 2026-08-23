"""Audit-log persistence."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from factory_core.domain.audit import AuditAction, AuditRequest
from factory_core.domain.ids import (
    ProjectId,
    UserId,
    new_project_id,
    new_user_id,
)
from factory_core.domain.pagination import PageRequest
from factory_core.persistence import (
    AuditRepository,
    ProjectRepository,
    UserRepository,
)

pytestmark = pytest.mark.integration


async def _make_user(session: AsyncSession, email: str = "ada@example.com") -> UserId:
    user = await UserRepository(session).create(
        user_id=new_user_id(),
        email=email,
        display_name="Ada Lovelace",
        password_hash="$argon2id$fake",
    )
    return user.id


class TestAuditRepository:
    async def test_records_and_reads_back(self, session: AsyncSession) -> None:
        owner = await _make_user(session)
        repo = AuditRepository(session)

        entry = await repo.record(
            AuditRequest.for_user(AuditAction.USER_SIGNED_IN, owner),
            request_id="req-1",
        )

        loaded = await repo.get(entry.id)
        assert loaded is not None
        assert loaded.action is AuditAction.USER_SIGNED_IN
        assert loaded.request_id == "req-1"

    @pytest.mark.security
    async def test_metadata_is_redacted_on_write(self, session: AsyncSession) -> None:
        """Audit rows are long-lived and widely read by operators."""
        owner = await _make_user(session)

        entry = await AuditRepository(session).record(
            AuditRequest.for_user(
                AuditAction.USER_SIGNED_IN, owner, password="hunter2", note="fine"
            )
        )

        assert entry.metadata["password"] != "hunter2"
        assert entry.metadata["note"] == "fine"

    async def test_survives_the_project_it_describes(self, session: AsyncSession) -> None:
        """No foreign key, so the record of a deletion outlives the deleted row."""
        owner = await _make_user(session)
        project_id: ProjectId = new_project_id()
        repo = ProjectRepository(session, owner_id=owner)
        await repo.create(project_id=project_id, name="Doomed", slug="doomed", description="")
        await AuditRepository(session).record(
            AuditRequest.for_project(AuditAction.PROJECT_DELETED, owner, project_id)
        )

        await repo.delete(project_id)

        page = await AuditRepository(session).list_for_project(project_id, PageRequest())
        assert page.total == 1
