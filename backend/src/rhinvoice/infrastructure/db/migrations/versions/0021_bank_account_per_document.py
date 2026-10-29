"""The bank account chosen per document, and accounts of third parties.

Existing accounts are the company's own and drafts keep paying to the default
account of their currency, so documents look as before (ADR 0037).

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-29 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HOLDER_ADDRESS = (
    ("holder_street", 70),
    ("holder_house_number", 16),
    ("holder_supplement", 70),
    ("holder_postal_code", 16),
    ("holder_city", 35),
    ("holder_country", 2),
)


def upgrade() -> None:
    op.add_column(
        "bank_accounts",
        sa.Column("third_party", sa.Boolean(), server_default="false", nullable=False),
    )
    for name, length in HOLDER_ADDRESS:
        op.add_column("bank_accounts", sa.Column(name, sa.String(length=length), nullable=True))
    op.create_check_constraint(
        op.f("ck_bank_accounts_third_party_address"),
        "bank_accounts",
        "NOT third_party OR holder_postal_code IS NOT NULL",
    )
    # Not frozen with the issued document: deleting the account clears it, the
    # snapshot keeps the account the document was issued with.
    op.add_column("documents", sa.Column("bank_account_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_documents_bank_account_id_bank_accounts"),
        "documents",
        "bank_accounts",
        ["bank_account_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Undo the columns; one way in practice once documents were issued with them.

    Issued documents keep their frozen snapshots: one with the footer "none" or a third
    party's account cannot be printed again by a version before 0.9.
    """
    op.drop_constraint(
        op.f("fk_documents_bank_account_id_bank_accounts"), "documents", type_="foreignkey"
    )
    op.drop_column("documents", "bank_account_id")
    op.drop_constraint(op.f("ck_bank_accounts_third_party_address"), "bank_accounts", type_="check")
    for name, _ in reversed(HOLDER_ADDRESS):
        op.drop_column("bank_accounts", name)
    op.drop_column("bank_accounts", "third_party")
    # Footers chose "none" from this version on; before, they listed the paying account.
    op.execute(
        "UPDATE print_layout SET footer_accounts = 'invoice_currency' "
        "WHERE footer_accounts = 'none'"
    )
