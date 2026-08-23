"""Repository foundations.

The important type here is ``ScopedRepository``. Every repository that touches
project-owned data derives from it, and it cannot be constructed without an owner. That
turns project isolation from a ``WHERE`` clause somebody has to remember into a
constructor argument the type checker demands — the difference between a convention and a
guarantee.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from factory_core.domain.ids import UserId


class Repository:
    """Base for repositories with no ownership dimension.

    Only used for globally-scoped tables such as ``users`` and ``audit_log``, where
    authorization is enforced by the calling service rather than by row ownership.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """The session this repository reads and writes through."""
        return self._session

    async def _count(self, statement: Select[Any]) -> int:
        """Count the rows a statement would return.

        Wrapping the statement in a subquery preserves its filters while discarding its
        ordering, which PostgreSQL rejects inside an aggregate over a subquery.
        """
        subquery = statement.order_by(None).subquery()
        result = await self._session.execute(select(func.count()).select_from(subquery))
        return int(result.scalar_one())


class ScopedRepository(Repository):
    """Base for repositories over data owned by exactly one user.

    Subclasses must apply :meth:`scope` to every statement they build. That is the whole
    contract: a subclass that forgets it leaks another user's rows, so ``test_isolation``
    exercises every read path.
    """

    def __init__(self, session: AsyncSession, *, owner_id: UserId) -> None:
        """Bind this repository to one owner.

        Args:
            session: Database session.
            owner_id: The user whose data this instance may touch.

        Raises:
            ValueError: ``owner_id`` was empty. Enforced at runtime as well as by typing
                because an unscoped repository is a data leak, and a ``None`` can still
                arrive from dynamically typed code.
        """
        if owner_id is None:
            # mypy calls this unreachable because the annotation is non-optional, and it
            # is right about typed callers. The guard is for untyped ones — a value
            # arriving from JSON or a test helper — where an unscoped repository would
            # silently return every user's rows.
            msg = "ScopedRepository requires an owner_id; an unscoped repository would leak data"  # type: ignore[unreachable]
            raise ValueError(msg)
        super().__init__(session)
        self._owner_id = owner_id

    @property
    def owner_id(self) -> UserId:
        """The owner this repository is scoped to."""
        return self._owner_id

    def scope(self, column: InstrumentedAttribute[Any]) -> ColumnElement[bool]:
        """Build the ownership predicate for this repository's owner.

        Args:
            column: The owning-user column of the table being queried.
        """
        predicate: ColumnElement[bool] = column == self._owner_id
        return predicate
