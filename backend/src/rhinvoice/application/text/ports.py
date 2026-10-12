from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from uuid import UUID

    from rhinvoice.domain.shared.language import Language
    from rhinvoice.domain.tax.treatment import TaxTreatment
    from rhinvoice.domain.text.template import TextTemplate


class TextTemplateRepository(Protocol):
    def list(self) -> list[TextTemplate]:
        """All templates, ordered by kind, document type, language and position."""
        ...

    def get(self, template_id: UUID) -> TextTemplate | None: ...
    def add(self, template: TextTemplate) -> None: ...
    def update(self, template: TextTemplate) -> None: ...
    def delete(self, template_id: UUID) -> None: ...


class LegalNoticeRepository(Protocol):
    def get(self, treatment: TaxTreatment, language: Language) -> str | None:
        """Return the company's own wording, or None for the built-in one."""
        ...

    def all(self) -> dict[tuple[TaxTreatment, Language], str]: ...
    def save(self, treatment: TaxTreatment, language: Language, text: str) -> None: ...
    def delete(self, treatment: TaxTreatment, language: Language) -> None: ...
