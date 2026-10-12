"""What the onboarding checklist remembers.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-11 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "onboarding",
        sa.Column("singleton", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("numbering_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("singleton", name=op.f("ck_onboarding_single_row")),
        sa.PrimaryKeyConstraint("singleton", name=op.f("pk_onboarding")),
    )


def downgrade() -> None:
    op.drop_table("onboarding")
