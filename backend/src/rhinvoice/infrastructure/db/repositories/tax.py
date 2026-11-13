"""The company's tax rates (ADR 0044)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import delete, func, insert, select, text, update

from rhinvoice.domain.tax.tax_rate import RateCategory, RateValue, TaxRate
from rhinvoice.infrastructure.db.tables import articles, document_lines, tax_rates

if TYPE_CHECKING:
    from sqlalchemy import Connection, RowMapping

    from rhinvoice.infrastructure.db.serialization import Json

# Recurring plans keep their lines in the JSON of their template.
_PLAN_RATES = text(
    "SELECT DISTINCT line ->> 'tax_rate_id' FROM recurring_plans, "
    "jsonb_array_elements(template -> 'lines') AS line "
    "WHERE line ->> 'tax_rate_id' IS NOT NULL"
)


class SqlTaxRateRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def list(self, *, for_update: bool = False) -> list[TaxRate]:
        statement = select(tax_rates).order_by(tax_rates.c.position)
        if for_update:
            statement = statement.with_for_update()
        return [_rate(row) for row in self._connection.execute(statement).mappings()]

    def add(self, rate: TaxRate) -> None:
        after = select(func.coalesce(func.max(tax_rates.c.position) + 1, 0)).scalar_subquery()
        self._connection.execute(insert(tax_rates).values(**_values(rate), position=after))

    def update(self, rate: TaxRate) -> None:
        self._connection.execute(
            update(tax_rates).where(tax_rates.c.id == rate.id).values(_values(rate))
        )

    def delete(self, rate_id: UUID) -> None:
        self._connection.execute(delete(tax_rates).where(tax_rates.c.id == rate_id))

    def used_ids(self) -> frozenset[UUID]:
        used: set[UUID] = set()
        for column in (document_lines.c.tax_rate_id, articles.c.tax_rate_id):
            used.update(
                self._connection.execute(select(column).where(column.is_not(None)).distinct())
                .scalars()
                .all()
            )
        used.update(UUID(value) for value in self._connection.execute(_PLAN_RATES).scalars())
        return frozenset(used)


def rate_values_to_json(values: tuple[RateValue, ...]) -> list[Json]:
    return [
        {"valid_from": value.valid_from.isoformat(), "percent": str(value.percent)}
        for value in values
    ]


def rate_values_from_json(data: list[Json]) -> tuple[RateValue, ...]:
    return tuple(
        RateValue(date.fromisoformat(value["valid_from"]), Decimal(value["percent"]))
        for value in data
    )


def _rate(row: RowMapping) -> TaxRate:
    return TaxRate(
        id=row["id"],
        name=row["name"],
        category=RateCategory(row["category"]),
        values=rate_values_from_json(row["rate_values"]),
        exemption_reason=row["exemption_reason"],
        notice=row["notice"],
        preset=row["preset"],
        hidden=row["hidden"],
    )


def _values(rate: TaxRate) -> dict[str, Any]:
    return {
        "id": rate.id,
        "name": rate.name,
        "category": rate.category.value,
        "rate_values": rate_values_to_json(rate.values),
        "exemption_reason": rate.exemption_reason,
        "notice": rate.notice,
        "preset": rate.preset,
        "hidden": rate.hidden,
    }
