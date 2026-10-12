"""Invoices of a program used before: their origin, further files and the import target.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-13 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
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


FROZEN_0014 = """
    type number customer_id currency language price_mode treatment discount_kind discount_value
    issue_date due_date service_from service_to subject reference intro_text closing_text
    issued_at snapshot issued_totals treatment_overridden created_at source_id payment_text
    goods_treatment
"""
FROZEN = FROZEN_0014 + " origin"

# Like the PDF of an issued document (0007): only added, and only with the hash it states.
PROTECT_ATTACHMENTS = """
CREATE FUNCTION rhinvoice_protect_document_attachments() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'attachments cannot be changed or deleted'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.sha256 <> encode(sha256(NEW.content), 'hex') THEN
        RAISE EXCEPTION 'the attachment does not match its hash'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF (SELECT status FROM documents WHERE id = NEW.document_id) = 'draft' THEN
        RAISE EXCEPTION 'drafts have no attachments'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER protect_document_attachments
    BEFORE INSERT OR UPDATE OR DELETE ON document_attachments
    FOR EACH ROW EXECUTE FUNCTION rhinvoice_protect_document_attachments();

CREATE FUNCTION rhinvoice_protect_document_attachments_truncate() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'attachments cannot be changed or deleted'
        USING ERRCODE = 'integrity_constraint_violation';
END $$;

CREATE TRIGGER protect_document_attachments_truncate BEFORE TRUNCATE ON document_attachments
    FOR EACH STATEMENT EXECUTE FUNCTION rhinvoice_protect_document_attachments_truncate();
"""


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("origin", sa.String(length=20), server_default="rhinvoice", nullable=False),
    )
    op.execute(_protect_document(FROZEN))
    op.create_table(
        "document_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_attachments_document_id_documents"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_attachments")),
    )
    op.create_index(
        op.f("ix_document_attachments_document_id"),
        "document_attachments",
        ["document_id"],
        unique=False,
    )
    op.execute(PROTECT_ATTACHMENTS)
    op.drop_constraint(op.f("ck_import_templates_target"), "import_templates", type_="check")
    op.create_check_constraint(
        op.f("ck_import_templates_target"),
        "import_templates",
        "target IN ('customers', 'articles', 'invoices')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM import_templates WHERE target = 'invoices'")
    op.drop_constraint(op.f("ck_import_templates_target"), "import_templates", type_="check")
    op.create_check_constraint(
        op.f("ck_import_templates_target"),
        "import_templates",
        "target IN ('customers', 'articles')",
    )
    op.execute("DROP TRIGGER protect_document_attachments_truncate ON document_attachments")
    op.execute("DROP FUNCTION rhinvoice_protect_document_attachments_truncate()")
    op.execute("DROP TRIGGER protect_document_attachments ON document_attachments")
    op.execute("DROP FUNCTION rhinvoice_protect_document_attachments()")
    op.drop_index(op.f("ix_document_attachments_document_id"), table_name="document_attachments")
    op.drop_table("document_attachments")
    op.execute(_protect_document(FROZEN_0014))
    op.drop_column("documents", "origin")
