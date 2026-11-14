"""Own units of the company (ADR 0046).

Every installation gets the 21 units of before as its units, in their order and with their
labels, also one without a company yet (articles may be saved before it). Articles, lines
and the lines of recurring plans refer to the unit of their stored code; a code that is not
one of the 21 gets a unit of its own. Issued lines keep their code and get the label they
printed with, in the document's language, so issued documents look the same.

The units are copied here as they were on the day of this migration: the domain's catalogue
may change later, a migration must not.

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-14 12:00:00.000000
"""

import json
import uuid
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

START: tuple[tuple[str, str, str, str, str], ...] = (
    ("C62", "Stk.", "pcs", "pce", "pz."),
    ("HUR", "Std.", "h", "h", "h"),
    ("MIN", "Min.", "min", "min", "min"),
    ("DAY", "Tag", "day", "jour", "giorno"),
    ("WEE", "Woche", "week", "semaine", "settimana"),
    ("MON", "Monat", "month", "mois", "mese"),
    ("ANN", "Jahr", "year", "année", "anno"),
    ("LS", "Pauschal", "lump sum", "forfait", "forfait"),
    ("KGM", "kg", "kg", "kg", "kg"),
    ("GRM", "g", "g", "g", "g"),
    ("TNE", "t", "t", "t", "t"),
    ("LTR", "l", "l", "l", "l"),
    ("MTR", "m", "m", "m", "m"),
    ("KMT", "km", "km", "km", "km"),
    ("MTK", "m²", "m²", "m²", "m²"),
    ("MTQ", "m³", "m³", "m³", "m³"),
    ("KWH", "kWh", "kWh", "kWh", "kWh"),
    ("SET", "Set", "set", "set", "set"),
    ("PR", "Paar", "pair", "paire", "paio"),
    ("XPK", "Paket", "package", "paquet", "pacco"),
    ("E48", "Leistung", "service unit", "prestation", "prestazione"),
)
"""Code and the labels of German, English, French and Italian documents, in their order."""
LANGUAGES: tuple[str, ...] = ("de", "en", "fr", "it")

# Lines may be written while their document is a draft only; this migration gives issued
# lines their unit too (code and label stay what they printed), as 0027 did with rates.
LINES_TRIGGER = "protect_document_lines"
FROZEN = "unit_frozen_whole"

type Labels = dict[str, dict[str, str]]
"""The label of each code per document language."""


def _seed(bind: sa.Connection) -> tuple[dict[str, uuid.UUID], Labels]:
    """Add the units of before and one for every other stored code; return them by code."""
    stored: set[str] = set(
        bind.execute(
            sa.text(
                "SELECT unit FROM articles UNION SELECT unit FROM document_lines "
                "WHERE unit IS NOT NULL UNION SELECT DISTINCT line ->> 'unit' "
                "FROM recurring_plans, jsonb_array_elements(template -> 'lines') AS line "
                "WHERE line ->> 'unit' IS NOT NULL"
            )
        ).scalars()
    )
    rows: list[tuple[str, dict[str, str]]] = [
        (code, dict(zip(LANGUAGES, (de, en, fr, it), strict=True)))
        for code, de, en, fr, it in START
    ]
    known = {code for code, _ in rows}
    # Never written by Rhinvoice, which knew the 21 only; such a code prints as it is.
    rows += [(code, dict.fromkeys(LANGUAGES, code)) for code in sorted(stored - known)]
    units: dict[str, uuid.UUID] = {}
    for position, (code, labels) in enumerate(rows):
        units[code] = uuid.uuid4()
        own = {
            language: label
            for language, label in labels.items()
            if language != "de" and label != labels["de"]
        }
        bind.execute(
            sa.text(
                "INSERT INTO units (id, code, label, labels, preset, position) "
                "VALUES (:id, :code, :label, CAST(:labels AS jsonb), :preset, :position)"
            ),
            {
                "id": units[code],
                "code": code,
                "label": labels["de"],
                "labels": json.dumps(own),
                "preset": code if code in known else None,
                "position": position,
            },
        )
    return units, dict(rows)


def _plan_lines(lines: list[dict[str, Any]], units: dict[str, uuid.UUID]) -> list[dict[str, Any]]:
    changed: list[dict[str, Any]] = []
    for line in lines:
        code = line.get("unit")
        rest = {name: value for name, value in line.items() if name != "unit"}
        changed.append({**rest, "unit_id": None if code is None else str(units[code])})
    return changed


def upgrade() -> None:
    op.create_table(
        "units",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=3), nullable=False),
        sa.Column("label", sa.String(length=20), nullable=False),
        sa.Column(
            "labels", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("description", sa.String(length=100), server_default="", nullable=False),
        sa.Column("preset", sa.String(length=3), nullable=True),
        sa.Column("hidden", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_units")),
    )
    op.create_index("uq_units_label", "units", [sa.text("lower(label)")], unique=True)
    op.create_index("uq_units_preset", "units", ["preset"], unique=True)
    bind = op.get_bind()
    units, labels = _seed(bind)
    mapping = json.dumps({code: str(unit_id) for code, unit_id in units.items()})
    by_code = "CAST(CAST(:units AS jsonb) ->> {column} AS uuid)"

    op.add_column("articles", sa.Column("unit_id", sa.Uuid(), nullable=True))
    bind.execute(
        sa.text(f"UPDATE articles SET unit_id = {by_code.format(column='unit')}"),  # noqa: S608 - constants
        {"units": mapping},
    )
    op.alter_column("articles", "unit_id", nullable=False)
    op.drop_column("articles", "unit")

    op.add_column("document_lines", sa.Column("unit_id", sa.Uuid(), nullable=True))
    op.add_column("document_lines", sa.Column("unit_label", sa.String(length=20), nullable=True))
    op.alter_column("document_lines", "unit", new_column_name="unit_code")
    op.execute(f"ALTER TABLE document_lines DISABLE TRIGGER {LINES_TRIGGER}")
    bind.execute(
        sa.text(
            f"UPDATE document_lines SET unit_id = {by_code.format(column='unit_code')} "  # noqa: S608 - constants
            "WHERE unit_code IS NOT NULL"
        ),
        {"units": mapping},
    )
    # Drafts use the current unit; issued lines keep the label of their language.
    op.execute(
        "UPDATE document_lines SET unit_code = NULL FROM documents "
        "WHERE documents.id = document_lines.document_id AND documents.status = 'draft'"
    )
    bind.execute(
        sa.text(
            "UPDATE document_lines SET unit_label = "
            "CAST(:labels AS jsonb) -> document_lines.unit_code ->> documents.language "
            "FROM documents WHERE documents.id = document_lines.document_id "
            "AND document_lines.unit_code IS NOT NULL"
        ),
        {"labels": json.dumps(labels)},
    )
    op.execute(f"ALTER TABLE document_lines ENABLE TRIGGER {LINES_TRIGGER}")
    op.create_check_constraint(
        op.f(f"ck_document_lines_{FROZEN}"),
        "document_lines",
        "(unit_code IS NULL) = (unit_label IS NULL)",
    )
    for table in ("articles", "document_lines"):
        op.create_foreign_key(
            op.f(f"fk_{table}_unit_id_units"),
            table,
            "units",
            ["unit_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index(op.f("ix_document_lines_unit_id"), "document_lines", ["unit_id"], unique=False)

    for plan_id, template in bind.execute(sa.text("SELECT id, template FROM recurring_plans")):
        bind.execute(
            sa.text(
                "UPDATE recurring_plans SET template = CAST(:template AS jsonb) WHERE id = :id"
            ),
            {
                "id": plan_id,
                "template": json.dumps(
                    {**template, "lines": _plan_lines(template["lines"], units)}
                ),
            },
        )


def downgrade() -> None:
    """Store the code of each unit again; the units go.

    The versions before knew the 21 units only: once a line, an article or a recurring plan
    uses a unit with another code, the downgrade stops.
    """
    bind = op.get_bind()
    codes = {str(row.id): row.code for row in bind.execute(sa.text("SELECT id, code FROM units"))}
    plans = list(bind.execute(sa.text("SELECT id, template FROM recurring_plans")))
    used = set(
        bind.execute(
            sa.text(
                "SELECT CAST(unit_id AS text) FROM document_lines WHERE unit_id IS NOT NULL "
                "UNION SELECT CAST(unit_id AS text) FROM articles"
            )
        ).scalars()
    )
    used.update(
        line["unit_id"]
        for _, template in plans
        for line in template["lines"]
        if line.get("unit_id") is not None
    )
    known = {code for code, *_ in START}
    # A plan may name a unit that is gone (its JSON has no foreign key): it had no code then.
    if any(unit in codes and codes[unit] not in known for unit in used):
        msg = (
            "documents, articles or recurring plans use own units: they need version 0.14 or later"
        )
        raise RuntimeError(msg)
    op.drop_index(op.f("ix_document_lines_unit_id"), table_name="document_lines")
    for table in ("document_lines", "articles"):
        op.drop_constraint(op.f(f"fk_{table}_unit_id_units"), table, type_="foreignkey")
    op.drop_constraint(op.f(f"ck_document_lines_{FROZEN}"), "document_lines", type_="check")
    op.execute(f"ALTER TABLE document_lines DISABLE TRIGGER {LINES_TRIGGER}")
    # Drafts name the code of their unit again; issued lines have theirs frozen.
    op.execute(
        "UPDATE document_lines SET unit_code = units.code FROM units "
        "WHERE units.id = document_lines.unit_id AND document_lines.unit_code IS NULL"
    )
    op.execute(f"ALTER TABLE document_lines ENABLE TRIGGER {LINES_TRIGGER}")
    op.alter_column("document_lines", "unit_code", new_column_name="unit")
    op.drop_column("document_lines", "unit_label")
    op.drop_column("document_lines", "unit_id")
    op.add_column("articles", sa.Column("unit", sa.String(length=3), nullable=True))
    op.execute("UPDATE articles SET unit = units.code FROM units WHERE units.id = articles.unit_id")
    op.alter_column("articles", "unit", nullable=False)
    op.drop_column("articles", "unit_id")
    for plan_id, template in plans:
        lines = [
            {
                **{name: value for name, value in line.items() if name != "unit_id"},
                "unit": codes.get(line.get("unit_id") or ""),
            }
            for line in template["lines"]
        ]
        bind.execute(
            sa.text(
                "UPDATE recurring_plans SET template = CAST(:template AS jsonb) WHERE id = :id"
            ),
            {"id": plan_id, "template": json.dumps({**template, "lines": lines})},
        )
    op.drop_index("uq_units_preset", table_name="units")
    op.drop_index("uq_units_label", table_name="units")
    op.drop_table("units")
