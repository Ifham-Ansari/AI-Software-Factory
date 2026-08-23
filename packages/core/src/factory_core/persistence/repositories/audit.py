"""Audit-log persistence.

Append-only by construction: this repository has no update or delete method, so there is
no code path through which an audit row can be altered.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Select, select

from factory_core.domain.audit import AuditAction, AuditEntry, AuditRequest
from factory_core.domain.ids import AuditEntryId, ProjectId, new_id
from factory_core.domain.pagination import Page, PageRequest
from factory_core.observability import get_redactor
from factory_core.persistence.mappers import to_audit_entry
from factory_core.persistence.models import AuditLogRow
from factory_core.persistence.repositories.base import Repository


class AuditRepository(Repository):
    """Writes and reads the audit trail."""

    async def record(
        self,
        request: AuditRequest,
        *,
        request_id: str | None = None,
        now: datetime | None = None,
    ) -> AuditEntry:
        """Append one audit entry.

        Metadata passes through the redactor on the way in. Audit rows are long-lived and
        widely readable by operators, so a credential that lands here is more exposed than
        one in a log line, not less.
        """
        redacted = get_redactor().redact(request.metadata)
        row = AuditLogRow(
            id=new_id(),
            actor_type=request.actor_type.value,
            actor_id=request.actor_id,
            action=request.action.value,
            resource_type=request.resource_type.value if request.resource_type else None,
            resource_id=request.resource_id,
            project_id=request.project_id,
            request_id=request_id,
            audit_metadata=redacted if isinstance(redacted, dict) else {},
            created_at=now or datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return to_audit_entry(row)

    async def get(self, entry_id: AuditEntryId) -> AuditEntry | None:
        """Load one audit entry."""
        row = await self._session.get(AuditLogRow, entry_id)
        return to_audit_entry(row) if row else None

    async def list_for_actor(self, actor_id: str, request: PageRequest) -> Page[AuditEntry]:
        """List entries attributed to one actor, newest first."""
        statement = select(AuditLogRow).where(AuditLogRow.actor_id == actor_id)
        return await self._page(statement, request)

    async def list_for_project(
        self, project_id: ProjectId, request: PageRequest
    ) -> Page[AuditEntry]:
        """List entries for one project, newest first."""
        statement = select(AuditLogRow).where(AuditLogRow.project_id == project_id)
        return await self._page(statement, request)

    async def count_by_action(self, action: AuditAction, *, actor_id: str | None = None) -> int:
        """Count entries for an action, optionally narrowed to one actor.

        Used by tests and by rate-limit style checks (for example, repeated failed
        sign-ins for one account).
        """
        statement = select(AuditLogRow).where(AuditLogRow.action == action.value)
        if actor_id is not None:
            statement = statement.where(AuditLogRow.actor_id == actor_id)
        return await self._count(statement)

    async def _page(
        self, statement: Select[tuple[AuditLogRow]], request: PageRequest
    ) -> Page[AuditEntry]:
        """Paginate an audit query, newest first with a stable tie-break."""
        total = await self._count(statement)
        if total == 0:
            return Page.empty(request)
        page_statement = (
            statement.order_by(AuditLogRow.created_at.desc(), AuditLogRow.id.asc())
            .offset(request.offset)
            .limit(request.limit)
        )
        result = await self._session.execute(page_statement)
        items = [to_audit_entry(row) for row in result.scalars().all()]
        return Page(items=items, total=total, page=request.page, page_size=request.page_size)
