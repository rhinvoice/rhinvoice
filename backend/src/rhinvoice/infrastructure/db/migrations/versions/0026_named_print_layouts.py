"""Several named print layouts, one the default, chosen per customer or document (#48).

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-11 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHOICES = (
    "template, logo_position, logo_size, font, sender_line, contact, position_numbers,"
    " footer_accounts, e_invoice, info_block"
)
# PrintLayout's defaults, for installations that never saved a layout.
DEFAULTS = "'modern', 'right', 'medium', 'sans', true, false, true, 'invoice_currency', true, NULL"


def upgrade() -> None:
    op.create_table(
        "print_layouts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("template", sa.String(length=20), nullable=False),
        sa.Column("logo_position", sa.String(length=10), nullable=False),
        sa.Column("logo_size", sa.String(length=10), nullable=False),
        sa.Column("font", sa.String(length=10), nullable=False),
        sa.Column("sender_line", sa.Boolean(), nullable=False),
        sa.Column("contact", sa.Boolean(), nullable=False),
        sa.Column("position_numbers", sa.Boolean(), nullable=False),
        sa.Column("footer_accounts", sa.String(length=20), nullable=False),
        sa.Column("e_invoice", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("info_block", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_print_layouts")),
        sa.UniqueConstraint("name", name=op.f("uq_print_layouts_name")),
    )
    op.create_index(
        "ix_print_layouts_one_default",
        "print_layouts",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    # The layout saved so far becomes the default one, named "Standard"; without one, the
    # defaults of the program, so documents look as before.
    op.execute(
        f"INSERT INTO print_layouts (id, name, is_default, {CHOICES}) "  # noqa: S608 - constants
        f"SELECT gen_random_uuid(), 'Standard', true, {CHOICES} FROM print_layout "
        f"UNION ALL SELECT gen_random_uuid(), 'Standard', true, {DEFAULTS} "
        "WHERE NOT EXISTS (SELECT 1 FROM print_layout)"
    )
    op.drop_table("print_layout")
    for table in ("customers", "documents"):
        op.add_column(table, sa.Column("print_layout_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            op.f(f"fk_{table}_print_layout_id_print_layouts"),
            table,
            "print_layouts",
            ["print_layout_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Keep the default layout as the single one; the other layouts and the choices go.

    Issued documents keep their layout in their snapshot and look the same.
    """
    for table in ("documents", "customers"):
        op.drop_constraint(
            op.f(f"fk_{table}_print_layout_id_print_layouts"), table, type_="foreignkey"
        )
        op.drop_column(table, "print_layout_id")
    op.execute("UPDATE recurring_plans SET template = template - 'print_layout_id'")
    op.create_table(
        "print_layout",
        sa.Column("singleton", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("template", sa.String(length=20), nullable=False),
        sa.Column("logo_position", sa.String(length=10), nullable=False),
        sa.Column("logo_size", sa.String(length=10), nullable=False),
        sa.Column("font", sa.String(length=10), nullable=False),
        sa.Column("sender_line", sa.Boolean(), nullable=False),
        sa.Column("contact", sa.Boolean(), nullable=False),
        sa.Column("position_numbers", sa.Boolean(), nullable=False),
        sa.Column("footer_accounts", sa.String(length=20), nullable=False),
        sa.Column("e_invoice", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("info_block", postgresql.JSONB(), nullable=True),
        sa.CheckConstraint("singleton", name=op.f("ck_print_layout_single_row")),
        sa.PrimaryKeyConstraint("singleton", name=op.f("pk_print_layout")),
    )
    op.execute(
        f"INSERT INTO print_layout (singleton, {CHOICES}) "  # noqa: S608 - constants
        f"SELECT true, {CHOICES} FROM print_layouts WHERE is_default"
    )
    op.drop_index("ix_print_layouts_one_default", table_name="print_layouts")
    op.drop_table("print_layouts")
