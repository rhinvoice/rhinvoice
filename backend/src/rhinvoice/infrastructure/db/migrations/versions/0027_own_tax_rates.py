"""Own tax rates of the company (ADR 0044).

The company gets the rates of its country, worded in its language: standard, reduced, the
special rate where the country has one, zero-rated and exempt. Every line, article and line
of a recurring plan that named one of these categories now refers to the rate of that preset;
reduced and special become the kind "standard" (any rate above zero). Pass-through items take
no rate. Issued lines keep their frozen percentages, so issued documents look the same.

The presets are copied here as they were on the day of this migration: the domain's presets
may change later, a migration must not.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-12 18:00:00.000000
"""

import json
import uuid
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KEYS = ("standard", "reduced", "special", "zero", "exempt")
"""The fixed categories of before, each now the key of a preset; in the order of the rates."""
TAXED = {"standard": "S", "reduced": "S", "special": "S", "zero": "Z", "exempt": "E"}
NAMES = {
    "standard": {
        "de": "Normalsatz",
        "en": "Standard rate",
        "fr": "Taux normal",
        "it": "Aliquota normale",
    },
    "reduced": {
        "de": "Reduzierter Satz",
        "en": "Reduced rate",
        "fr": "Taux réduit",
        "it": "Aliquota ridotta",
    },
    "zero": {
        "de": "0 % (steuerbar)",
        "en": "0 % (taxable)",
        "fr": "0 % (imposable)",
        "it": "0 % (imponibile)",
    },
    "exempt": {
        "de": "Von der Steuer ausgenommen",
        "en": "Exempt",
        "fr": "Exclu du champ de l’impôt",  # noqa: RUF001 - French apostrophe
        "it": "Escluso dall’imposta",  # noqa: RUF001 - Italian apostrophe
    },
}
SWISS_SPECIAL = {
    "de": "Sondersatz Beherbergung",
    "en": "Accommodation rate",
    "fr": "Taux spécial pour l’hébergement",  # noqa: RUF001 - French apostrophe
    "it": "Aliquota speciale per il settore alberghiero",
}
SPECIAL_NAMES = {
    "CH": SWISS_SPECIAL,
    "LI": SWISS_SPECIAL,
    "AT": {
        "de": "Zweiter ermäßigter Satz",
        "en": "Second reduced rate",
        "fr": "Deuxième taux réduit",
        "it": "Seconda aliquota ridotta",
    },
}
EXEMPTION_REASONS = {
    "de": "Steuerbefreite Leistung",
    "en": "Exempt supply",
    "fr": "Prestation exonérée",
    "it": "Prestazione esente",
}
type Values = dict[str, tuple[tuple[str, str], ...]]
"""Per key: the dates and percentages of the rate."""
SWISS_VALUES: Values = {
    "standard": (("2011-01-01", "8"), ("2018-01-01", "7.7"), ("2024-01-01", "8.1")),
    "reduced": (("2011-01-01", "2.5"), ("2024-01-01", "2.6")),
    "special": (("2011-01-01", "3.8"), ("2018-01-01", "3.7"), ("2024-01-01", "3.8")),
    "zero": (("2011-01-01", "0"),),
    "exempt": (("2011-01-01", "0"),),
}
VALUES: dict[str, Values] = {
    "CH": SWISS_VALUES,
    "LI": SWISS_VALUES,
    "DE": {
        "standard": (("2007-01-01", "19"), ("2020-07-01", "16"), ("2021-01-01", "19")),
        "reduced": (("2007-01-01", "7"), ("2020-07-01", "5"), ("2021-01-01", "7")),
        "zero": (("2007-01-01", "0"),),
        "exempt": (("2007-01-01", "0"),),
    },
    "AT": {
        "standard": (("2016-01-01", "20"),),
        "reduced": (("2016-01-01", "10"),),
        "special": (("2016-01-01", "13"),),
        "zero": (("2016-01-01", "0"),),
        "exempt": (("2016-01-01", "0"),),
    },
}
"""The dated percentages of the profiles (ADR 0017), one value per change."""

NEEDS_RATE = "tax_category IN ('standard', 'reduced', 'special', 'zero', 'exempt')"
# Lines may be written while their document is a draft only; this migration changes the
# reference of issued lines too (their frozen percentage stays), as 0023 did with events.
LINES_TRIGGER = "protect_document_lines"


def _seed(bind: sa.Connection) -> dict[str, uuid.UUID]:
    """Add the presets of the company's country; return the rate of each key."""
    company = bind.execute(sa.text("SELECT country, default_language FROM company")).first()
    if company is None:
        return {}
    country, language = company.country, company.default_language
    rates: dict[str, uuid.UUID] = {}
    for key, values in VALUES[country].items():
        names = SPECIAL_NAMES[country] if key == "special" else NAMES[key]
        rates[key] = uuid.uuid4()
        bind.execute(
            sa.text(
                "INSERT INTO tax_rates (id, name, category, rate_values, exemption_reason, "
                "preset, position) VALUES (:id, :name, :category, CAST(:rate_values AS jsonb), "
                ":reason, :preset, :position)"
            ),
            {
                "id": rates[key],
                "name": names[language],
                "category": TAXED[key],
                "rate_values": json.dumps(
                    [{"valid_from": since, "percent": percent} for since, percent in values]
                ),
                "reason": EXEMPTION_REASONS[language] if key == "exempt" else "",
                "preset": key,
                "position": len(rates) - 1,
            },
        )
    return rates


def _rate_for(rates: dict[str, uuid.UUID], category: str) -> uuid.UUID:
    # A special rate where the country has none could never be calculated: the standard
    # rate takes its place.
    return rates.get(category) or rates["standard"]


def _plan_lines(lines: list[dict[str, Any]], rates: dict[str, uuid.UUID]) -> list[dict[str, Any]]:
    changed: list[dict[str, Any]] = []
    for line in lines:
        category = line["tax_category"]
        rate = None
        if line["kind"] == "item" and category in TAXED:
            rate = str(_rate_for(rates, category))
            category = "standard" if TAXED[category] == "S" else category
        changed.append({**line, "tax_category": category, "tax_rate_id": rate})
    return changed


def upgrade() -> None:
    op.create_table(
        "tax_rates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("category", sa.String(length=1), nullable=False),
        sa.Column("rate_values", postgresql.JSONB(), nullable=False),
        sa.Column("exemption_reason", sa.String(length=300), server_default="", nullable=False),
        sa.Column("notice", sa.String(length=300), server_default="", nullable=False),
        sa.Column("preset", sa.String(length=40), nullable=True),
        sa.Column("hidden", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("category IN ('S', 'Z', 'E')", name=op.f("ck_tax_rates_category")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tax_rates")),
    )
    op.create_index("uq_tax_rates_name", "tax_rates", [sa.text("lower(name)")], unique=True)
    op.create_index("uq_tax_rates_preset", "tax_rates", ["preset"], unique=True)
    for table in ("articles", "document_lines"):
        op.add_column(table, sa.Column("tax_rate_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            op.f(f"fk_{table}_tax_rate_id_tax_rates"),
            table,
            "tax_rates",
            ["tax_rate_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index(
        op.f("ix_document_lines_tax_rate_id"), "document_lines", ["tax_rate_id"], unique=False
    )
    bind = op.get_bind()
    rates = _seed(bind)
    if not rates:
        # Documents need a company; articles could be saved before it, but have no country.
        orphans = bind.execute(sa.text(f"SELECT count(*) FROM articles WHERE {NEEDS_RATE}"))  # noqa: S608 - constants
        if orphans.scalar_one():
            msg = "articles exist without a company: set up the company with version 0.12 first"
            raise RuntimeError(msg)
        return
    op.execute(f"ALTER TABLE document_lines DISABLE TRIGGER {LINES_TRIGGER}")
    for table, items in (("articles", "TRUE"), ("document_lines", "kind = 'item'")):
        for category, code in TAXED.items():
            bind.execute(
                sa.text(
                    f"UPDATE {table} SET tax_rate_id = :rate, tax_category = :kind "  # noqa: S608 - constants
                    f"WHERE {items} AND tax_category = :category AND tax_rate_id IS NULL"
                ),
                {
                    "rate": _rate_for(rates, category),
                    "kind": "standard" if code == "S" else category,
                    "category": category,
                },
            )
    op.execute(f"ALTER TABLE document_lines ENABLE TRIGGER {LINES_TRIGGER}")
    for plan_id, template in bind.execute(sa.text("SELECT id, template FROM recurring_plans")):
        bind.execute(
            sa.text(
                "UPDATE recurring_plans SET template = CAST(:template AS jsonb) WHERE id = :id"
            ),
            {
                "id": plan_id,
                "template": json.dumps(
                    {**template, "lines": _plan_lines(template["lines"], rates)}
                ),
            },
        )


def downgrade() -> None:
    """Name the category of each rate's preset again; the rates go.

    Own rates and the presets of special schemes have no category of before: once a line,
    an article or a recurring plan uses one, the downgrade stops.
    """
    bind = op.get_bind()
    keys = {
        str(row.id): row.preset for row in bind.execute(sa.text("SELECT id, preset FROM tax_rates"))
    }
    plans = list(bind.execute(sa.text("SELECT id, template FROM recurring_plans")))
    used = set(
        bind.execute(
            sa.text(
                "SELECT CAST(tax_rate_id AS text) FROM document_lines "
                "WHERE tax_rate_id IS NOT NULL UNION "
                "SELECT CAST(tax_rate_id AS text) FROM articles WHERE tax_rate_id IS NOT NULL"
            )
        ).scalars()
    )
    used.update(
        line["tax_rate_id"]
        for _, template in plans
        for line in template["lines"]
        if line.get("tax_rate_id") is not None
    )
    if any(keys.get(rate) not in KEYS for rate in used):
        msg = (
            "documents, articles or recurring plans use own tax rates: "
            "they need version 0.13 or later"
        )
        raise RuntimeError(msg)
    op.execute(f"ALTER TABLE document_lines DISABLE TRIGGER {LINES_TRIGGER}")
    for table in ("articles", "document_lines"):
        op.execute(
            f"UPDATE {table} SET tax_category = tax_rates.preset FROM tax_rates "  # noqa: S608 - constants
            f"WHERE tax_rates.id = {table}.tax_rate_id"
        )
    op.execute(f"ALTER TABLE document_lines ENABLE TRIGGER {LINES_TRIGGER}")
    for plan_id, template in plans:
        lines = [
            {
                **{name: value for name, value in line.items() if name != "tax_rate_id"},
                "tax_category": (
                    line["tax_category"]
                    if line.get("tax_rate_id") is None
                    else keys[line["tax_rate_id"]]
                ),
            }
            for line in template["lines"]
        ]
        bind.execute(
            sa.text(
                "UPDATE recurring_plans SET template = CAST(:template AS jsonb) WHERE id = :id"
            ),
            {"id": plan_id, "template": json.dumps({**template, "lines": lines})},
        )
    op.drop_index(op.f("ix_document_lines_tax_rate_id"), table_name="document_lines")
    for table in ("document_lines", "articles"):
        op.drop_constraint(op.f(f"fk_{table}_tax_rate_id_tax_rates"), table, type_="foreignkey")
        op.drop_column(table, "tax_rate_id")
    op.drop_index("uq_tax_rates_preset", table_name="tax_rates")
    op.drop_index("uq_tax_rates_name", table_name="tax_rates")
    op.drop_table("tax_rates")
