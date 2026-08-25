"""ORM models for the secret vault and project configuration requirements.

Separate from ``models.py`` so neither file outgrows a screenful. These four tables share
one concern — what a project needs to be configured and what it has been given — and are
mutually referential enough to belong together.

Nothing here stores a plaintext value. ``secrets.ciphertext`` is AES-256-GCM output bound
to its project and name; ``project_keys.wrapped_dek`` is a DEK sealed under the master
key. Neither is readable without key material that lives only in the environment.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from factory_core.persistence.base import Base, TimestampMixin, uuid_pk
from factory_core.persistence.models import JsonDict


class ProjectKeyRow(Base, TimestampMixin):
    """The wrapped data encryption key for one project.

    Exactly one row per project. ``wrapped_dek`` carries its KEK version inline
    (``v1:base64...``), so a rotation sweep can find rows still on a retired key with a
    prefix match rather than trying to decrypt each one.
    """

    __tablename__ = "project_keys"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    wrapped_dek: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[str] = mapped_column(String(32), nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        # One DEK per project. A second row would mean half a project's secrets were
        # encrypted under a key the other half cannot read.
        UniqueConstraint("project_id", name="uq_project_keys_project_id"),
        # The rotation sweep selects by version.
        Index("ix_project_keys_key_version", "key_version"),
    )


class SecretRow(Base, TimestampMixin):
    """One encrypted credential belonging to a project.

    There is no plaintext column and no view that produces one. Reads go through the
    vault, which requires a declared sink and writes an access-log row.
    """

    __tablename__ = "secrets"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Recorded so a rotation sweep knows which values need re-encrypting, and so a
    # decrypt failure can be attributed to a specific key generation.
    key_version: Mapped[str] = mapped_column(String(32), nullable=False)
    last_accessed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    version: Mapped[int] = mapped_column(nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_secrets_project_id_name"),
        Index("ix_secrets_project_id_created_at", "project_id", "created_at"),
        CheckConstraint("version >= 1", name="version_positive"),
    )


class SecretAccessLogRow(Base):
    """An append-only record of every secret resolution.

    Written inside the same transaction as the resolution it describes, so a value cannot
    be read without the row existing. Append-only and without a foreign key to
    ``secrets``: the log must outlive the secret, which is exactly when it matters.
    """

    __tablename__ = "secret_access_log"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    secret_name: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Which allowlisted sink asked for it.
    sink: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Free-text reason supplied by the caller, e.g. "deploy to staging".
    purpose: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: False when the attempt was refused; a denied resolution is the interesting one.
    granted: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        Index("ix_secret_access_log_project_id_created_at", "project_id", "created_at"),
        Index("ix_secret_access_log_run_id", "run_id"),
    )


class ConfigRequirementRow(Base, TimestampMixin):
    """One credential or setting a project needs before it can be built or deployed.

    The catalog of *what* a requirement means is code (see
    ``factory_core.domain.config_requirements``); this table records which requirements a
    given project has, and whether each is satisfied. Satisfaction is derived from the
    presence of the matching secret, not stored as a duplicate truth.
    """

    __tablename__ = "config_requirements"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    required: Mapped[bool] = mapped_column(nullable=False, default=True)
    #: True when the requirement is met by something other than a secret, e.g. a plan
    #: choice the user made. Secret-backed requirements derive satisfaction instead.
    satisfied_at: Mapped[datetime | None] = mapped_column(nullable=True)
    requirement_metadata: Mapped[dict[str, Any]] = mapped_column(
        JsonDict, nullable=False, default=dict
    )

    __table_args__ = (
        UniqueConstraint("project_id", "key", name="uq_config_requirements_project_id_key"),
        Index("ix_config_requirements_project_id_category", "project_id", "category"),
    )
