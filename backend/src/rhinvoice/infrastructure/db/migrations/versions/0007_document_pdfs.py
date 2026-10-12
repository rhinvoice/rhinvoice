"""Archived PDFs of issued documents.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-11 04:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The PDF is part of the issued document (GoBD, OR 958f, BAO 131): it is only
# added, never changed or removed, and it must match the hash on the document.
PROTECT = """
CREATE FUNCTION rhinvoice_protect_document_pdfs() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    expected text;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'archived PDFs cannot be changed or deleted'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    SELECT pdf_sha256 INTO expected FROM documents WHERE id = NEW.document_id;
    IF expected IS NULL OR expected <> encode(sha256(NEW.content), 'hex') THEN
        RAISE EXCEPTION 'the PDF does not match the hash of its document'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER protect_document_pdfs BEFORE INSERT OR UPDATE OR DELETE ON document_pdfs
    FOR EACH ROW EXECUTE FUNCTION rhinvoice_protect_document_pdfs();

CREATE FUNCTION rhinvoice_protect_document_pdfs_truncate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'archived PDFs cannot be changed or deleted'
        USING ERRCODE = 'integrity_constraint_violation';
END $$;

CREATE TRIGGER protect_document_pdfs_truncate BEFORE TRUNCATE ON document_pdfs
    FOR EACH STATEMENT EXECUTE FUNCTION rhinvoice_protect_document_pdfs_truncate();
"""


def upgrade() -> None:
    op.create_table(
        "document_pdfs",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_pdfs_document_id_documents"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("document_id", name=op.f("pk_document_pdfs")),
    )
    op.execute(PROTECT)


def downgrade() -> None:
    op.execute("DROP TRIGGER protect_document_pdfs_truncate ON document_pdfs")
    op.execute("DROP FUNCTION rhinvoice_protect_document_pdfs_truncate()")
    op.execute("DROP TRIGGER protect_document_pdfs ON document_pdfs")
    op.execute("DROP FUNCTION rhinvoice_protect_document_pdfs()")
    op.drop_table("document_pdfs")
