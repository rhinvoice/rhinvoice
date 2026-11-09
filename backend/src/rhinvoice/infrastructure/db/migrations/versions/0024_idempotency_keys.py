"""Requests repeated with the same Idempotency-Key run once (ADR 0041).

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-06 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=10), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status_code", sa.SmallInteger(), nullable=True),
        sa.Column("body", sa.LargeBinary(), nullable=True),
        sa.CheckConstraint("state IN ('running', 'done')", name=op.f("ck_idempotency_keys_state")),
        sa.CheckConstraint(
            "state = 'running' OR status_code IS NOT NULL",
            name=op.f("ck_idempotency_keys_done_status"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_idempotency_keys_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "key", name=op.f("pk_idempotency_keys")),
    )
    op.create_index(
        op.f("ix_idempotency_keys_started_at"), "idempotency_keys", ["started_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_idempotency_keys_started_at"), table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
