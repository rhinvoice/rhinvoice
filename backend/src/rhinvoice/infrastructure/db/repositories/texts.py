"""Text templates and the company's wording of legal notices."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import case, delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.tax.treatment import TaxTreatment
from rhinvoice.domain.text.template import TextKind, TextTemplate
from rhinvoice.infrastructure.db.tables import legal_notices, text_templates

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy import Connection, RowMapping


def _template_from_row(row: RowMapping) -> TextTemplate:
    return TextTemplate(
        id=row["id"],
        kind=TextKind(row["kind"]),
        document_type=DocumentType(row["document_type"]),
        language=Language(row["language"]),
        name=row["name"],
        text=row["text"],
        is_default=row["is_default"],
        position=row["position"],
    )


def _template_values(template: TextTemplate) -> dict[str, object]:
    return {
        "id": template.id,
        "kind": template.kind.value,
        "document_type": template.document_type.value,
        "language": template.language.value,
        "name": template.name,
        "text": template.text,
        "is_default": template.is_default,
        "position": template.position,
    }


# The order texts appear on a document.
_KIND_ORDER = case(
    {kind.value: index for index, kind in enumerate(TextKind)}, value=text_templates.c.kind
)


class SqlTextTemplateRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def list(self) -> list[TextTemplate]:
        statement = select(text_templates).order_by(
            text_templates.c.document_type,
            text_templates.c.language,
            _KIND_ORDER,
            text_templates.c.position,
            text_templates.c.id,
        )
        return [_template_from_row(row) for row in self._connection.execute(statement).mappings()]

    def get(self, template_id: UUID) -> TextTemplate | None:
        statement = select(text_templates).where(text_templates.c.id == template_id)
        row = self._connection.execute(statement).mappings().first()
        return None if row is None else _template_from_row(row)

    def add(self, template: TextTemplate) -> None:
        self._connection.execute(insert(text_templates).values(_template_values(template)))

    def update(self, template: TextTemplate) -> None:
        self._connection.execute(
            update(text_templates)
            .where(text_templates.c.id == template.id)
            .values(_template_values(template)),
        )

    def delete(self, template_id: UUID) -> None:
        self._connection.execute(delete(text_templates).where(text_templates.c.id == template_id))


class SqlLegalNoticeRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get(self, treatment: TaxTreatment, language: Language) -> str | None:
        statement = select(legal_notices.c.text).where(
            legal_notices.c.treatment == treatment.value,
            legal_notices.c.language == language.value,
        )
        return self._connection.execute(statement).scalar_one_or_none()

    def all(self) -> dict[tuple[TaxTreatment, Language], str]:
        rows = self._connection.execute(select(legal_notices)).mappings()
        return {
            (TaxTreatment(row["treatment"]), Language(row["language"])): row["text"] for row in rows
        }

    def save(self, treatment: TaxTreatment, language: Language, text: str) -> None:
        statement = pg_insert(legal_notices).values(
            treatment=treatment.value, language=language.value, text=text
        )
        self._connection.execute(
            statement.on_conflict_do_update(
                index_elements=[legal_notices.c.treatment, legal_notices.c.language],
                set_={"text": statement.excluded.text},
            ),
        )

    def delete(self, treatment: TaxTreatment, language: Language) -> None:
        self._connection.execute(
            delete(legal_notices).where(
                legal_notices.c.treatment == treatment.value,
                legal_notices.c.language == language.value,
            ),
        )
