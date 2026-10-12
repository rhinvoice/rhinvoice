"""Saved column mappings of the import."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, func, insert, select

from rhinvoice.application.importing.fields import ImportTarget
from rhinvoice.application.importing.ports import ImportTemplate
from rhinvoice.infrastructure.db.tables import import_templates

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy import Connection, RowMapping


def _template_from_row(row: RowMapping) -> ImportTemplate:
    return ImportTemplate(
        id=row["id"],
        target=ImportTarget(row["target"]),
        name=row["name"],
        columns=dict(row["columns"]),
        created_at=row["created_at"],
    )


class SqlImportTemplateRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def list(self, target: ImportTarget) -> list[ImportTemplate]:
        rows = self._connection.execute(
            select(import_templates)
            .where(import_templates.c.target == target.value)
            .order_by(func.lower(import_templates.c.name)),
        ).mappings()
        return [_template_from_row(row) for row in rows]

    def get(self, template_id: UUID) -> ImportTemplate | None:
        row = (
            self._connection.execute(
                select(import_templates).where(import_templates.c.id == template_id),
            )
            .mappings()
            .first()
        )
        return None if row is None else _template_from_row(row)

    def name_exists(self, target: ImportTarget, name: str) -> bool:
        condition = (import_templates.c.target == target.value) & (
            func.lower(import_templates.c.name) == name.lower()
        )
        return self._connection.execute(select(func.count()).where(condition)).scalar_one() > 0

    def add(self, template: ImportTemplate) -> None:
        self._connection.execute(
            insert(import_templates).values(
                id=template.id,
                target=template.target.value,
                name=template.name,
                columns=dict(template.columns),
                created_at=template.created_at,
            ),
        )

    def delete(self, template_id: UUID) -> None:
        self._connection.execute(
            delete(import_templates).where(import_templates.c.id == template_id)
        )
