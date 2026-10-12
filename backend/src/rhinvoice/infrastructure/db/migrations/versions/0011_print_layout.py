"""How documents are laid out on paper.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-11 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "print_layout",
        sa.Column("singleton", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("template", sa.String(length=20), nullable=False),
        sa.Column("logo_position", sa.String(length=10), nullable=False),
        sa.Column("logo_size", sa.String(length=10), nullable=False),
        sa.Column("font", sa.String(length=10), nullable=False),
        sa.Column("sender_line", sa.Boolean(), nullable=False),
        sa.Column("contact", sa.Boolean(), nullable=False),
        sa.Column("position_numbers", sa.Boolean(), nullable=False),
        sa.Column("footer_accounts", sa.String(length=20), nullable=False),
        sa.CheckConstraint("singleton", name=op.f("ck_print_layout_single_row")),
        sa.PrimaryKeyConstraint("singleton", name=op.f("pk_print_layout")),
    )


def downgrade() -> None:
    op.drop_table("print_layout")
