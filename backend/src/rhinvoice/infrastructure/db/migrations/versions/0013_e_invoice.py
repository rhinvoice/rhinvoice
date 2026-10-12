"""E-invoices: embedded in the PDF by default, archived with it.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-11 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "print_layout",
        sa.Column("e_invoice", sa.Boolean(), server_default="true", nullable=False),
    )
    # The CII XML in the archived PDF, kept beside it (insert only, like the PDF).
    op.add_column("document_pdfs", sa.Column("e_invoice", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("document_pdfs", "e_invoice")
    op.drop_column("print_layout", "e_invoice")
