"""Recurring invoices: the plans and the invoices they wrote.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-12 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recurring_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("interval", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("next_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("service_period", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("template", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_recurring_plans_customer_id_customers"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "interval IN ('monthly', 'quarterly', 'half_yearly', 'yearly')",
            name=op.f("ck_recurring_plans_interval"),
        ),
        sa.CheckConstraint(
            "action IN ('draft', 'issue', 'send')", name=op.f("ck_recurring_plans_action")
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date", name=op.f("ck_recurring_plans_end")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recurring_plans")),
    )
    op.create_table(
        "recurring_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(length=10), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(length=50), server_default="", nullable=False),
        sa.Column("message", sa.String(length=500), server_default="", nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_recurring_runs_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["recurring_plans.id"],
            name=op.f("fk_recurring_runs_plan_id_recurring_plans"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "outcome IN ('draft', 'issued', 'sent', 'failed')",
            name=op.f("ck_recurring_runs_outcome"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recurring_runs")),
        sa.UniqueConstraint("plan_id", "period_start", name="uq_recurring_runs_plan_period"),
    )


def downgrade() -> None:
    op.drop_table("recurring_runs")
    op.drop_table("recurring_plans")
