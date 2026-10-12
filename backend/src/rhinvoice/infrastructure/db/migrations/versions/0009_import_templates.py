"""Saved column mappings of the import.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-11 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("target", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("columns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "target IN ('customers', 'articles')", name=op.f("ck_import_templates_target")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_templates")),
        sa.UniqueConstraint("target", "name", name="uq_import_templates_target_name"),
    )


def downgrade() -> None:
    op.drop_table("import_templates")
