"""Logos of issued documents.

Issuing keeps the company's logo under its SHA-256, so a PDF made later (when it
could not be archived right away) shows the logo of the day of issuing (ADR 0007).
Like the archived PDFs, a kept logo is only added, never changed or removed.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-31 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROTECT = """
CREATE FUNCTION rhinvoice_protect_issued_logos() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'logos of issued documents cannot be changed or deleted'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.sha256 <> encode(sha256(NEW.content), 'hex') THEN
        RAISE EXCEPTION 'the logo does not match its hash'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER protect_issued_logos BEFORE INSERT OR UPDATE OR DELETE ON issued_logos
    FOR EACH ROW EXECUTE FUNCTION rhinvoice_protect_issued_logos();
CREATE FUNCTION rhinvoice_protect_issued_logos_truncate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'logos of issued documents cannot be changed or deleted'
        USING ERRCODE = 'integrity_constraint_violation';
END $$;
CREATE TRIGGER protect_issued_logos_truncate BEFORE TRUNCATE ON issued_logos
    FOR EACH STATEMENT EXECUTE FUNCTION rhinvoice_protect_issued_logos_truncate();
"""


def upgrade() -> None:
    op.create_table(
        "issued_logos",
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=50), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint("sha256", name=op.f("pk_issued_logos")),
    )
    op.execute(PROTECT)


def downgrade() -> None:
    # Documents issued meanwhile keep the fingerprint in their snapshot; without the
    # table they print today's logo, as before.
    op.execute("DROP TRIGGER protect_issued_logos_truncate ON issued_logos")
    op.execute("DROP FUNCTION rhinvoice_protect_issued_logos_truncate()")
    op.execute("DROP TRIGGER protect_issued_logos ON issued_logos")
    op.execute("DROP FUNCTION rhinvoice_protect_issued_logos()")
    op.drop_table("issued_logos")
