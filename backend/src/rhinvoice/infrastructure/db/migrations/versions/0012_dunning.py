"""Dunning levels and payment reminders.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-11 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEVEL = "level BETWEEN 1 AND 3"


def upgrade() -> None:
    op.create_table(
        "dunning_levels",
        sa.Column("level", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("days_after_due", sa.SmallInteger(), nullable=False),
        sa.Column("payment_days", sa.SmallInteger(), nullable=False),
        sa.Column("fee", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("text_de", sa.Text(), nullable=False),
        sa.Column("text_en", sa.Text(), nullable=False),
        sa.CheckConstraint(LEVEL, name=op.f("ck_dunning_levels_level")),
        sa.PrimaryKeyConstraint("level", name=op.f("pk_dunning_levels")),
    )
    op.create_table(
        "reminders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("open_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("fee", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.CheckConstraint(LEVEL, name=op.f("ck_reminders_level")),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["documents.id"],
            name=op.f("fk_reminders_invoice_id_documents"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminders")),
        sa.UniqueConstraint("invoice_id", "level", name="uq_reminders_invoice_level"),
    )


def downgrade() -> None:
    op.drop_table("reminders")
    op.drop_table("dunning_levels")
