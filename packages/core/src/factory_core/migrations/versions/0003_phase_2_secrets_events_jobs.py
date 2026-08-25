"""Phase 2: secret vault, configuration requirements, events and the job queue.

Revision ID: 0003
Revises: 0002
Created: 2026-08-24

Six tables, three concerns:

* ``project_keys``, ``secrets``, ``secret_access_log`` - the envelope-encrypted vault.
  No column holds plaintext; ``secrets.ciphertext`` is AES-256-GCM output and
  ``project_keys.wrapped_dek`` is a data key sealed under the master key.
* ``config_requirements`` - what each project still needs before it can be built.
* ``workflow_runs``, ``workflow_events``, ``jobs`` - the execution record and the durable
  queue. ``uq_workflow_events_run_id_seq`` is the replay contract, and
  ``ix_jobs_status_run_after`` is what keeps the SKIP LOCKED claim an index scan.

Purely additive: no existing table is altered, so the downgrade is a clean drop and
Phase 1 data is untouched either way.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_by", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'dead')",
            name=op.f("ck_jobs_status_valid"),
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_jobs_attempts_non_negative")),
        sa.CheckConstraint("max_attempts >= 1", name=op.f("ck_jobs_max_attempts_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.UniqueConstraint("idempotency_key", name="uq_jobs_idempotency_key"),
    )
    op.create_index(
        "ix_jobs_project_id_created_at", "jobs", ["project_id", "created_at"], unique=False
    )
    op.create_index(
        "ix_jobs_status_lease_expires_at", "jobs", ["status", "lease_expires_at"], unique=False
    )
    op.create_index("ix_jobs_status_run_after", "jobs", ["status", "run_after"], unique=False)
    op.create_table(
        "secret_access_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("secret_name", sa.String(length=64), nullable=False),
        sa.Column("sink", sa.String(length=32), nullable=False),
        sa.Column("purpose", sa.String(length=200), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_secret_access_log")),
    )
    op.create_index(
        "ix_secret_access_log_project_id_created_at",
        "secret_access_log",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_secret_access_log_run_id", "secret_access_log", ["run_id"], unique=False)
    op.create_table(
        "config_requirements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("satisfied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "requirement_metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_config_requirements_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_config_requirements")),
        sa.UniqueConstraint("project_id", "key", name="uq_config_requirements_project_id_key"),
    )
    op.create_index(
        "ix_config_requirements_project_id_category",
        "config_requirements",
        ["project_id", "category"],
        unique=False,
    )
    op.create_table(
        "project_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("wrapped_dek", sa.Text(), nullable=False),
        sa.Column("key_version", sa.String(length=32), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_keys_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_keys")),
        sa.UniqueConstraint("project_id", name="uq_project_keys_project_id"),
    )
    op.create_index("ix_project_keys_key_version", "project_keys", ["key_version"], unique=False)
    op.create_table(
        "secrets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("key_version", sa.String(length=32), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_secrets_version_positive")),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_secrets_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_secrets")),
        sa.UniqueConstraint("project_id", "name", name="uq_secrets_project_id_name"),
    )
    op.create_index(
        "ix_secrets_project_id_created_at", "secrets", ["project_id", "created_at"], unique=False
    )
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("last_seq", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name=op.f("ck_workflow_runs_status_valid"),
        ),
        sa.CheckConstraint("last_seq >= 0", name=op.f("ck_workflow_runs_last_seq_non_negative")),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_workflow_runs_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_runs")),
    )
    op.create_index(
        "ix_workflow_runs_project_id_created_at",
        "workflow_runs",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "workflow_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("seq > 0", name=op.f("ck_workflow_events_seq_positive")),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_workflow_events_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_events")),
        sa.UniqueConstraint("run_id", "seq", name="uq_workflow_events_run_id_seq"),
    )
    op.create_index(
        "ix_workflow_events_project_id_occurred_at",
        "workflow_events",
        ["project_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    """Revert the migration.

    Every migration must be reversible. A migration that cannot be undone is a migration
    that cannot be safely deployed.
    """
    op.drop_index("ix_workflow_events_project_id_occurred_at", table_name="workflow_events")
    op.drop_table("workflow_events")
    op.drop_index("ix_workflow_runs_project_id_created_at", table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_index("ix_secrets_project_id_created_at", table_name="secrets")
    op.drop_table("secrets")
    op.drop_index("ix_project_keys_key_version", table_name="project_keys")
    op.drop_table("project_keys")
    op.drop_index("ix_config_requirements_project_id_category", table_name="config_requirements")
    op.drop_table("config_requirements")
    op.drop_index("ix_secret_access_log_run_id", table_name="secret_access_log")
    op.drop_index("ix_secret_access_log_project_id_created_at", table_name="secret_access_log")
    op.drop_table("secret_access_log")
    op.drop_index("ix_jobs_status_run_after", table_name="jobs")
    op.drop_index("ix_jobs_status_lease_expires_at", table_name="jobs")
    op.drop_index("ix_jobs_project_id_created_at", table_name="jobs")
    op.drop_table("jobs")
