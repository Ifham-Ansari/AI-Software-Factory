"""SQLAlchemy declarative base and shared column conventions.

The naming convention matters more than it looks. Without it, PostgreSQL invents
constraint names and Alembic's autogenerate produces migrations that try to drop and
recreate constraints it cannot identify. With it, every index, constraint and key has a
deterministic name derived from its columns, so autogenerate diffs are stable and
reviewable.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, MetaData, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
        uuid.UUID: Uuid(as_uuid=True),
    }

    def __repr__(self) -> str:
        identifier = getattr(self, "id", None)
        return f"<{type(self).__name__} id={identifier}>"


def uuid_pk() -> Mapped[uuid.UUID]:
    """A UUID primary key column.

    Values are generated in the domain layer rather than by the database, so an entity
    has its identity before it is persisted. That lets a service emit an audit entry
    referencing a row it is creating in the same transaction.
    """
    return mapped_column(Uuid(as_uuid=True), primary_key=True)


def created_at_column() -> Mapped[datetime]:
    """Creation timestamp, defaulted by the database."""
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


def updated_at_column() -> Mapped[datetime]:
    """Last-modified timestamp, maintained by the ORM on flush."""
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TimestampMixin:
    """Adds ``created_at`` and ``updated_at`` to a model."""

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
