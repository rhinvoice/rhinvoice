"""Sending by mail: the mail server and the company's mail templates.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-12 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mail_server",
        sa.Column("singleton", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("host", sa.String(length=253), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("security", sa.String(length=10), nullable=False),
        sa.Column("sender", sa.String(length=254), nullable=False),
        sa.Column("sender_name", sa.String(length=120), server_default="", nullable=False),
        sa.Column("username", sa.String(length=254), server_default="", nullable=False),
        sa.Column("password", sa.String(length=500), server_default="", nullable=False),
        sa.Column("reply_to", sa.String(length=254), nullable=True),
        sa.Column("copy_to_sender", sa.Boolean(), nullable=False),
        sa.CheckConstraint("singleton", name=op.f("ck_mail_server_single_row")),
        sa.CheckConstraint(
            "security IN ('starttls', 'tls', 'none')", name=op.f("ck_mail_server_security")
        ),
        sa.PrimaryKeyConstraint("singleton", name=op.f("pk_mail_server")),
    )
    op.create_table(
        "mail_templates",
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("kind", "language", name=op.f("pk_mail_templates")),
    )


def downgrade() -> None:
    op.drop_table("mail_templates")
    op.drop_table("mail_server")
