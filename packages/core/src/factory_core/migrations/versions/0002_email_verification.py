"""Email verification: verified timestamp on users, and one-time codes.

Revision ID: 0002
Revises: 0001
Created: 2026-08-23

Existing accounts are backfilled as verified. They were created before verification
existed, so treating them as unverified would lock out every current user for a rule they
had no way to satisfy. New accounts start unverified.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add verification state and the code table."""
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Grandfather existing accounts: they predate the requirement.
    op.execute("UPDATE users SET email_verified_at = now() WHERE email_verified_at IS NULL")

    op.create_table(
        "email_verifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_email_verifications"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_email_verifications_user_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'consumed', 'expired', 'exhausted')",
            name="status_valid",
        ),
        sa.CheckConstraint("attempts >= 0", name="attempts_non_negative"),
    )
    op.create_index(
        "ix_email_verifications_user_id_issued_at",
        "email_verifications",
        ["user_id", "issued_at"],
    )


def downgrade() -> None:
    """Remove verification state and the code table."""
    op.drop_index(
        "ix_email_verifications_user_id_issued_at", table_name="email_verifications"
    )
    op.drop_table("email_verifications")
    op.drop_column("users", "email_verified_at")
