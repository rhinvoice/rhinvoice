"""A fixed buyer reference per customer (Leitweg-ID of German authorities).

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-16 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column("buyer_reference", sa.String(length=100), server_default="", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("customers", "buyer_reference")
