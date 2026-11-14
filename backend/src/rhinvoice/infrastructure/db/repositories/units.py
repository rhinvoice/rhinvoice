"""The company's units (ADR 0046)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import bindparam, delete, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError

from rhinvoice.domain.catalog.unit import Unit
from rhinvoice.infrastructure.db.tables import articles, document_lines, units

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Connection, RowMapping

# Recurring plans keep their lines in the JSON of their template.
_PLAN_UNITS = text(
    "SELECT DISTINCT line ->> 'unit_id' FROM recurring_plans, "
    "jsonb_array_elements(template -> 'lines') AS line "
    "WHERE line ->> 'unit_id' IS NOT NULL"
)


class SqlUnitRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def list(self, *, for_update: bool = False) -> list[Unit]:
        statement = select(units).order_by(units.c.position)
        if for_update:
            statement = statement.with_for_update()
        return [_unit(row) for row in self._connection.execute(statement).mappings()]

    def add(self, unit: Unit) -> None:
        after = select(func.coalesce(func.max(units.c.position) + 1, 0)).scalar_subquery()
        self._connection.execute(insert(units).values(**_values(unit), position=after))

    def update(self, unit: Unit) -> None:
        self._connection.execute(update(units).where(units.c.id == unit.id).values(_values(unit)))

    def delete(self, unit_id: UUID) -> bool:
        # In a savepoint: a refused delete leaves the transaction usable, e.g. to hide the unit.
        # Deleting a unit can only break a foreign key (lines and articles RESTRICT it).
        try:
            with self._connection.begin_nested():
                self._connection.execute(delete(units).where(units.c.id == unit_id))
        except IntegrityError:
            return False
        return True

    def reorder(self, unit_ids: Sequence[UUID]) -> None:
        if unit_ids:
            self._connection.execute(
                update(units)
                .where(units.c.id == bindparam("unit_id"))
                .values(position=bindparam("new_position")),
                [
                    {"unit_id": unit_id, "new_position": position}
                    for position, unit_id in enumerate(unit_ids)
                ],
            )

    def used_ids(self) -> frozenset[UUID]:
        used: set[UUID] = set()
        for column in (document_lines.c.unit_id, articles.c.unit_id):
            used.update(
                self._connection.execute(select(column).where(column.is_not(None)).distinct())
                .scalars()
                .all()
            )
        used.update(UUID(value) for value in self._connection.execute(_PLAN_UNITS).scalars())
        return frozenset(used)


def _unit(row: RowMapping) -> Unit:
    labels: dict[str, str] = row["labels"]
    return Unit(
        id=row["id"],
        code=row["code"],
        label=row["label"],
        label_en=labels.get("en", ""),
        label_fr=labels.get("fr", ""),
        label_it=labels.get("it", ""),
        description=row["description"],
        preset=row["preset"],
        hidden=row["hidden"],
    )


def _values(unit: Unit) -> dict[str, Any]:
    return {
        "id": unit.id,
        "code": unit.code,
        "label": unit.label,
        "labels": {language.value: label for language, label in unit.translations.items()},
        "description": unit.description,
        "preset": unit.preset,
        "hidden": unit.hidden,
    }
