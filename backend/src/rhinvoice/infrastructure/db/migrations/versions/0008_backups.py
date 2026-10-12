"""Backup requests of the app and runs of the backup container.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-11 05:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REASONS = "reason IN ('daily', 'document', 'manual')"


def upgrade() -> None:
    op.create_table(
        "backup_requests",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=20), nullable=False),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(REASONS, name=op.f("ck_backup_requests_reason")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backup_requests")),
    )
    op.create_index(
        "ix_backup_requests_pending",
        "backup_requests",
        ["requested_at"],
        postgresql_where=sa.text("handled_at IS NULL"),
    )
    op.create_table(
        "backup_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("snapshot_id", sa.String(length=64), nullable=True),
        sa.Column("data_added", sa.BigInteger(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.CheckConstraint(REASONS, name=op.f("ck_backup_runs_reason")),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'not_configured')",
            name=op.f("ck_backup_runs_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backup_runs")),
    )


def downgrade() -> None:
    op.drop_table("backup_runs")
    op.drop_index("ix_backup_requests_pending", table_name="backup_requests")
    op.drop_table("backup_requests")
