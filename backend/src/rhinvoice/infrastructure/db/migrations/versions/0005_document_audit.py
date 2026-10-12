"""Quote conversions, a wider immutability check and an append-only audit trail.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-11 00:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
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


FROZEN_0004 = """
    type number customer_id currency language price_mode treatment discount_kind discount_value
    issue_date due_date service_from service_to subject reference intro_text closing_text
    issued_at snapshot issued_totals
"""
FROZEN = FROZEN_0004 + " treatment_overridden created_at source_id"

AUDIT_TRAIL = """
CREATE FUNCTION rhinvoice_protect_document_events() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    parent_status text;
BEGIN
    SELECT status INTO parent_status FROM documents WHERE id = OLD.document_id;
    IF parent_status IS NOT NULL AND parent_status <> 'draft' THEN
        RAISE EXCEPTION 'the history of issued documents is append-only'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;

CREATE TRIGGER protect_document_events BEFORE UPDATE OR DELETE ON document_events
    FOR EACH ROW EXECUTE FUNCTION rhinvoice_protect_document_events();

CREATE FUNCTION rhinvoice_protect_document_payments() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- Payments are recorded or removed (both logged as events), never edited.
    RAISE EXCEPTION 'payments cannot be changed, only removed'
        USING ERRCODE = 'integrity_constraint_violation';
END $$;

CREATE TRIGGER protect_document_payments BEFORE UPDATE ON document_payments
    FOR EACH ROW EXECUTE FUNCTION rhinvoice_protect_document_payments();
"""


def upgrade() -> None:
    op.add_column("documents", sa.Column("converted_to_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_documents_converted_to_id_documents"),
        "documents",
        "documents",
        ["converted_to_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(_protect_document(FROZEN))
    op.execute(AUDIT_TRAIL)


def downgrade() -> None:
    op.execute("DROP TRIGGER protect_document_payments ON document_payments")
    op.execute("DROP FUNCTION rhinvoice_protect_document_payments()")
    op.execute("DROP TRIGGER protect_document_events ON document_events")
    op.execute("DROP FUNCTION rhinvoice_protect_document_events()")
    op.execute(_protect_document(FROZEN_0004))
    op.drop_constraint(
        op.f("fk_documents_converted_to_id_documents"), "documents", type_="foreignkey"
    )
    op.drop_column("documents", "converted_to_id")
