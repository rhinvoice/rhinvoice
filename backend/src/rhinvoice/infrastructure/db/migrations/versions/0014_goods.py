"""Goods and services: the supply of articles and lines, the treatment of goods.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-12 08:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _protect_document(frozen_columns: str) -> str:
    """Build the document trigger function; ``frozen_columns`` are fixed once issued."""
    old = ", ".join(f"OLD.{column}" for column in frozen_columns.split())
    new = ", ".join(f"NEW.{column}" for column in frozen_columns.split())
    return f"""
CREATE OR REPLACE FUNCTION rhinvoice_protect_document() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status = 'draft' THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'issued documents cannot be deleted'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF ({old}) IS DISTINCT FROM ({new})
       OR NEW.status = 'draft'
       OR (OLD.pdf_sha256 IS NOT NULL AND NEW.pdf_sha256 IS DISTINCT FROM OLD.pdf_sha256)
    THEN
        RAISE EXCEPTION 'issued documents are immutable'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END $$;
"""


FROZEN_0006 = """
    type number customer_id currency language price_mode treatment discount_kind discount_value
    issue_date due_date service_from service_to subject reference intro_text closing_text
    issued_at snapshot issued_totals treatment_overridden created_at source_id payment_text
"""
FROZEN = FROZEN_0006 + " goods_treatment"


def upgrade() -> None:
    # Everything so far was a service: the only kind Rhinvoice knew.
    op.add_column(
        "articles",
        sa.Column("supply", sa.String(length=10), server_default="service", nullable=False),
    )
    op.add_column(
        "document_lines",
        sa.Column("supply", sa.String(length=10), server_default="service", nullable=False),
    )
    # NULL: the goods follow the document's treatment (documents without goods lines).
    op.add_column("documents", sa.Column("goods_treatment", sa.String(length=20), nullable=True))
    op.execute(_protect_document(FROZEN))


def downgrade() -> None:
    op.execute(_protect_document(FROZEN_0006))
    op.drop_column("documents", "goods_treatment")
    op.drop_column("document_lines", "supply")
    op.drop_column("articles", "supply")
