"""Optional and alternative positions of quotes (ADR 0045).

A line counts into the total ("yes"), is offered on top ("optional") or instead of another
line of its quote ("alternative", naming that line). Existing lines count, as they did.

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-13 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK = "alternative_names_its_position"
KNOWN = "in_total_known"


def upgrade() -> None:
    op.add_column(
        "document_lines",
        sa.Column("in_total", sa.String(length=12), server_default="yes", nullable=False),
    )
    op.add_column("document_lines", sa.Column("alternative_to", sa.Uuid(), nullable=True))
    op.create_check_constraint(
        op.f(f"ck_document_lines_{KNOWN}"),
        "document_lines",
        "in_total IN ('yes', 'optional', 'alternative')",
    )
    op.create_check_constraint(
        op.f(f"ck_document_lines_{CHECK}"),
        "document_lines",
        "(in_total = 'alternative') = (alternative_to IS NOT NULL)",
    )


def downgrade() -> None:
    """Drop the columns; a line outside the total would count again, so the downgrade stops."""
    outside = op.get_bind().execute(
        sa.text("SELECT count(*) FROM document_lines WHERE in_total <> 'yes'")
    )
    if outside.scalar_one():
        msg = "quotes hold optional or alternative positions: they need version 0.13 or later"
        raise RuntimeError(msg)
    op.drop_constraint(op.f(f"ck_document_lines_{CHECK}"), "document_lines", type_="check")
    op.drop_constraint(op.f(f"ck_document_lines_{KNOWN}"), "document_lines", type_="check")
    op.drop_column("document_lines", "alternative_to")
    op.drop_column("document_lines", "in_total")
