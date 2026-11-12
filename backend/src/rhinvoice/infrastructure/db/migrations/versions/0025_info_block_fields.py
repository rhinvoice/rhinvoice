"""The facts next to the address: rows a layout lists, shows or hides, and fields with values.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-11 12:00:00.000000
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _protect_document(frozen_columns: str) -> str:
    """Build the document trigger function; ``frozen_columns`` are fixed once issued (0017)."""
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


FROZEN_0017 = """
    type number customer_id currency language price_mode treatment discount_kind discount_value
    issue_date due_date service_from service_to subject reference intro_text closing_text
    issued_at snapshot issued_totals treatment_overridden created_at source_id payment_text
    goods_treatment origin
"""
FROZEN = FROZEN_0017 + " fields"

# The rows as documents printed them before layouts listed them (PrintLayout's default).
OLD_ROWS = json.dumps(
    [
        {"key": key, "shown": True, "label": ""}
        for key in ("number", "customer_number", "date", "due_date", "service_date", "reference")
    ]
)


def upgrade() -> None:
    op.add_column("print_layout", sa.Column("info_block", postgresql.JSONB(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("fields", postgresql.JSONB(), server_default="[]", nullable=False),
    )
    op.execute(_protect_document(FROZEN))


def downgrade() -> None:
    """Drop the fields and the rows of layouts.

    Drafts and recurring plans lose their field values, and the layout shows every row
    again. Issued documents are never changed: once one holds a field value or was issued
    with other rows than the old ones, the downgrade stops.
    """
    bind = op.get_bind()
    issued = bind.execute(
        sa.text(
            "SELECT count(*) FROM documents WHERE status <> 'draft' AND ("
            "fields <> '[]'::jsonb OR (snapshot -> 'layout' ? 'info_block' "
            "AND snapshot -> 'layout' -> 'info_block' <> CAST(:rows AS jsonb)))"
        ),
        {"rows": OLD_ROWS},
    )
    if issued.scalar_one():
        msg = "issued documents print fields or other rows: they need the version that added them"
        raise RuntimeError(msg)
    op.execute(_protect_document(FROZEN_0017))
    op.drop_column("documents", "fields")
    op.drop_column("print_layout", "info_block")
    op.execute("UPDATE recurring_plans SET template = template - 'fields'")
