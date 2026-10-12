"""Text templates, legal notices and the payment text of documents.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-11 03:00:00.000000
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
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


FROZEN_0005 = """
    type number customer_id currency language price_mode treatment discount_kind discount_value
    issue_date due_date service_from service_to subject reference intro_text closing_text
    issued_at snapshot issued_totals treatment_overridden created_at source_id
"""
FROZEN = FROZEN_0005 + " payment_text"

# Ready-made templates, so that new documents get sensible texts from the start.
# Placeholders: {nummer} {datum} {faellig} {kunde} {betrag} {waehrung}.
SEEDS: list[tuple[str, str, str, str, str, bool]] = [
    # kind, document type, language, name, text, default
    (
        "intro",
        "invoice",
        "de",
        "Dank für den Auftrag",
        (
            "Vielen Dank für Ihren Auftrag. Wir erlauben uns, Ihnen folgende Leistungen"
            " in Rechnung zu stellen:"
        ),
        True,
    ),
    ("payment", "invoice", "de", "Fällig am", "Zahlbar bis {faellig}.", True),
    (
        "payment",
        "invoice",
        "de",
        "Rechnungsnummer als Verwendungszweck",
        (
            "Bei Überweisung mittels Internet-Banking tragen Sie bitte im Feld"
            " «Verwendungszweck» die Rechnungsnummer {nummer} ein."
        ),
        True,
    ),
    (
        "payment",
        "invoice",
        "de",
        "Zahlbar prompt ohne Abzug",
        "Zahlbar prompt und ohne Abzug.",
        False,
    ),
    (
        "closing",
        "invoice",
        "de",
        "Dank für die Zusammenarbeit",
        "Wir danken für die angenehme Zusammenarbeit.",
        True,
    ),
    (
        "intro",
        "quote",
        "de",
        "Angebot",
        "Vielen Dank für Ihre Anfrage. Gerne unterbreiten wir Ihnen folgendes Angebot:",
        True,
    ),
    (
        "closing",
        "quote",
        "de",
        "Gültigkeit",
        "Dieses Angebot ist gültig bis {faellig}. Wir freuen uns auf Ihren Auftrag.",
        True,
    ),
    (
        "intro",
        "invoice",
        "en",
        "Thank you for the order",
        "Thank you for your order. Please find our invoice for the following services:",
        True,
    ),
    ("payment", "invoice", "en", "Due date", "Payable by {faellig}.", True),
    (
        "payment",
        "invoice",
        "en",
        "Invoice number as reference",
        "Please quote the invoice number {nummer} as the payment reference.",
        True,
    ),
    ("closing", "invoice", "en", "Thanks", "Thank you for your business.", True),
    (
        "intro",
        "quote",
        "en",
        "Quote",
        "Thank you for your enquiry. We are pleased to offer you the following:",
        True,
    ),
    (
        "closing",
        "quote",
        "en",
        "Validity",
        "This quote is valid until {faellig}. We look forward to your order.",
        True,
    ),
]


def upgrade() -> None:
    op.add_column(
        "documents", sa.Column("payment_text", sa.Text(), server_default="", nullable=False)
    )
    op.execute(_protect_document(FROZEN))
    templates = op.create_table(
        "text_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("document_type", sa.String(length=20), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("name", sa.String(length=70), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_text_templates")),
    )
    op.create_table(
        "legal_notices",
        sa.Column("treatment", sa.String(length=20), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("treatment", "language", name=op.f("pk_legal_notices")),
    )
    positions: dict[tuple[str, str, str], int] = {}
    rows: list[dict[str, object]] = []
    for kind, document_type, language, name, text, is_default in SEEDS:
        key = (kind, document_type, language)
        positions[key] = positions.get(key, -1) + 1
        rows.append(
            {
                "id": uuid.uuid4(),
                "kind": kind,
                "document_type": document_type,
                "language": language,
                "name": name,
                "text": text,
                "is_default": is_default,
                "position": positions[key],
            },
        )
    op.bulk_insert(templates, rows)


def downgrade() -> None:
    op.drop_table("legal_notices")
    op.drop_table("text_templates")
    op.execute(_protect_document(FROZEN_0005))
    op.drop_column("documents", "payment_text")
