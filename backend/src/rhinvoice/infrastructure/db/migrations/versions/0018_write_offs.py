"""Write-offs of invoices that will not be paid.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-13 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Like payments (0005): recorded or (logged) taken back, never edited.
PROTECT_WRITE_OFFS = """
CREATE FUNCTION rhinvoice_protect_document_write_offs() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'write-offs cannot be changed, only removed'
        USING ERRCODE = 'integrity_constraint_violation';
END $$;

CREATE TRIGGER protect_document_write_offs BEFORE UPDATE ON document_write_offs
    FOR EACH ROW EXECUTE FUNCTION rhinvoice_protect_document_write_offs();
"""


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "written_off_amount",
            sa.Numeric(precision=14, scale=2),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_table(
        "document_write_offs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("written_off_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("reason", sa.String(length=20), nullable=False),
        sa.Column("note", sa.String(length=500), server_default="", nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name=op.f("ck_document_write_offs_amount_positive")),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_write_offs_document_id_documents"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_write_offs")),
        sa.UniqueConstraint("document_id", name=op.f("uq_document_write_offs_document_id")),
    )
    op.execute(PROTECT_WRITE_OFFS)


# Without the status, a written-off invoice is open again with what was lost of it.
REOPEN = """
UPDATE documents SET
    open_amount = written_off_amount,
    status = CASE
        WHEN EXISTS (SELECT 1 FROM document_payments WHERE document_id = documents.id)
        THEN 'partially_paid' ELSE 'issued'
    END
WHERE status = 'written_off'
"""


def downgrade() -> None:
    op.execute(REOPEN)
    op.execute("DROP TRIGGER protect_document_write_offs ON document_write_offs")
    op.execute("DROP FUNCTION rhinvoice_protect_document_write_offs()")
    op.drop_table("document_write_offs")
    op.drop_column("documents", "written_off_amount")
