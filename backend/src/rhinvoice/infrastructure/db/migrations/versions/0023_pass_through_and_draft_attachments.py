"""Pass-through items and attachments of drafts.

The tax category "pass_through" is longer than the ten characters the column took
(ADR 0039). Drafts take attachments, which may be removed while the document is a
draft; from issuing on they are only added, never changed or removed (ADR 0040).

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-30 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORY_TABLES = ("articles", "document_lines")
BACK_TO_EXEMPT = {
    "articles": "UPDATE articles SET tax_category = 'exempt' WHERE tax_category = 'pass_through'",
    "document_lines": (
        "UPDATE document_lines SET tax_category = 'exempt' WHERE tax_category = 'pass_through'"
    ),
}
# Recurring plans keep their lines in the JSON of their template; the order stays.
PLANS_BACK_TO_EXEMPT = """
UPDATE recurring_plans SET template = jsonb_set(
    template,
    '{lines}',
    (
        SELECT jsonb_agg(
            CASE WHEN line ->> 'tax_category' = 'pass_through'
                THEN jsonb_set(line, '{tax_category}', '"exempt"')
                ELSE line
            END
            ORDER BY position
        )
        FROM jsonb_array_elements(template -> 'lines') WITH ORDINALITY AS lines (line, position)
    )
)
WHERE template -> 'lines' @> '[{"tax_category": "pass_through"}]'
"""

# The document row is read FOR SHARE: issuing the draft at the same moment waits for the
# upload (or the upload for the issuing), so no file slips onto an issued document.
PROTECT_ATTACHMENTS = """
CREATE OR REPLACE FUNCTION rhinvoice_protect_document_attachments() RETURNS trigger
    LANGUAGE plpgsql AS $$
DECLARE
    parent record;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'attachments cannot be changed or deleted'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    SELECT status, origin INTO parent FROM documents
        WHERE id = CASE WHEN TG_OP = 'DELETE' THEN OLD.document_id ELSE NEW.document_id END
        FOR SHARE;
    IF TG_OP = 'DELETE' THEN
        IF parent.status IS DISTINCT FROM 'draft' THEN
            RAISE EXCEPTION 'attachments cannot be changed or deleted'
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        RETURN OLD;
    END IF;
    IF NEW.sha256 <> encode(sha256(NEW.content), 'hex') THEN
        RAISE EXCEPTION 'the attachment does not match its hash'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF parent.status IS DISTINCT FROM 'draft' AND parent.origin IS DISTINCT FROM 'imported' THEN
        RAISE EXCEPTION 'issued documents take no further attachments'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END $$;
"""

# As in 0017: only added, never to drafts.
PROTECT_ATTACHMENTS_0017 = """
CREATE OR REPLACE FUNCTION rhinvoice_protect_document_attachments() RETURNS trigger
    LANGUAGE plpgsql AS $$
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
"""


def upgrade() -> None:
    for table in CATEGORY_TABLES:
        op.alter_column(
            table,
            "tax_category",
            existing_type=sa.String(length=10),
            type_=sa.String(length=20),
            existing_nullable=False,
        )
    op.execute(PROTECT_ATTACHMENTS)


def downgrade() -> None:
    """Undo the wider column and the attachments of drafts.

    Drafts lose their attachments; their pass-through lines, such articles and the lines of
    recurring plans fall back to "exempt", the category without VAT closest to them. Issued
    documents are never changed: once one holds a pass-through line, the downgrade stops.
    """
    issued = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM document_lines JOIN documents ON documents.id = document_id "
            "WHERE tax_category = 'pass_through' AND status <> 'draft'"
        )
    )
    if issued.scalar_one():
        msg = "issued documents hold pass-through items: they need version 0.9 or later"
        raise RuntimeError(msg)
    op.execute(PROTECT_ATTACHMENTS_0017)
    op.execute("ALTER TABLE document_attachments DISABLE TRIGGER protect_document_attachments")
    op.execute(
        "DELETE FROM document_attachments WHERE document_id IN "
        "(SELECT id FROM documents WHERE status = 'draft')"
    )
    op.execute("ALTER TABLE document_attachments ENABLE TRIGGER protect_document_attachments")
    op.execute(PLANS_BACK_TO_EXEMPT)
    for table in CATEGORY_TABLES:
        op.execute(BACK_TO_EXEMPT[table])
        op.alter_column(
            table,
            "tax_category",
            existing_type=sa.String(length=20),
            type_=sa.String(length=10),
            existing_nullable=False,
        )
