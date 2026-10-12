"""Use cases of text templates (Textbausteine) and legal notices."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from rhinvoice.application.errors import NotFoundError
from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.text import clean_multiline
from rhinvoice.domain.text.notice import MAX_NOTICE
from rhinvoice.domain.text.template import TextTemplate

if TYPE_CHECKING:
    from uuid import UUID

    from rhinvoice.application.uow import UnitOfWork, UnitOfWorkFactory
    from rhinvoice.domain.document.document import DocumentType
    from rhinvoice.domain.shared.country import Country
    from rhinvoice.domain.tax.treatment import TaxTreatment
    from rhinvoice.domain.text.template import TextKind


@dataclass(frozen=True, slots=True)
class SaveTextTemplate:
    kind: TextKind
    document_type: DocumentType
    language: Language
    name: str
    text: str
    is_default: bool = False


@dataclass(frozen=True, slots=True)
class LegalNotice:
    treatment: TaxTreatment
    language: Language
    text: str
    """The wording printed on documents."""
    default_text: str
    """The built-in wording for the company's country."""
    customized: bool


def effective_notice(
    uow: UnitOfWork, treatment: TaxTreatment, country: Country, language: Language
) -> str:
    """Return the notice printed for a treatment: the company's wording or the built-in one."""
    if treatment not in profile_of(country).notice_treatments:
        return ""
    own = uow.legal_notices.get(treatment, language)
    return profile_of(country).notice(treatment, language) if own is None else own


@dataclass(frozen=True, slots=True)
class TextHandlers:
    uow: UnitOfWorkFactory

    # --- Templates ---------------------------------------------------------------

    def list_templates(self) -> list[TextTemplate]:
        with self.uow() as uow:
            return uow.text_templates.list()

    def create_template(self, command: SaveTextTemplate) -> TextTemplate:
        with self.uow() as uow:
            template = self._build(new_id(), command, self._next_position(uow, command))
            uow.text_templates.add(template)
            uow.commit()
        return template

    def update_template(self, template_id: UUID, command: SaveTextTemplate) -> TextTemplate:
        with self.uow() as uow:
            existing = self._require(uow, template_id)
            moved = (existing.kind, existing.document_type, existing.language) != (
                command.kind,
                command.document_type,
                command.language,
            )
            # A template moved to another group goes to the end of that group.
            position = self._next_position(uow, command) if moved else existing.position
            template = self._build(existing.id, command, position)
            uow.text_templates.update(template)
            uow.commit()
        return template

    def move_template(self, template_id: UUID, *, up: bool) -> list[TextTemplate]:
        """Swap a template with its neighbour of the same kind, type and language."""
        with self.uow() as uow:
            template = self._require(uow, template_id)
            siblings = sorted(
                (
                    sibling
                    for sibling in uow.text_templates.list()
                    if (sibling.kind, sibling.document_type, sibling.language)
                    == (template.kind, template.document_type, template.language)
                ),
                key=lambda sibling: sibling.position,
            )
            index = siblings.index(template)
            other = index - 1 if up else index + 1
            if 0 <= other < len(siblings):
                neighbour = siblings[other]
                uow.text_templates.update(replace(template, position=neighbour.position))
                uow.text_templates.update(replace(neighbour, position=template.position))
                uow.commit()
            return uow.text_templates.list()

    def delete_template(self, template_id: UUID) -> None:
        with self.uow() as uow:
            self._require(uow, template_id)
            uow.text_templates.delete(template_id)
            uow.commit()

    # --- Legal notices -----------------------------------------------------------

    def list_notices(self) -> list[LegalNotice]:
        with self.uow() as uow:
            country = self._country(uow)
            own = uow.legal_notices.all()
            notices: list[LegalNotice] = []
            for treatment in profile_of(country).notice_treatments:
                for language in Language:
                    default = profile_of(country).notice(treatment, language)
                    text = own.get((treatment, language))
                    notices.append(
                        LegalNotice(
                            treatment=treatment,
                            language=language,
                            text=default if text is None else text,
                            default_text=default,
                            customized=text is not None,
                        ),
                    )
            return notices

    def save_notice(self, treatment: TaxTreatment, language: Language, text: str) -> LegalNotice:
        """Use the company's own wording; an empty text restores the built-in one."""
        cleaned = clean_multiline(text, "text", max_length=MAX_NOTICE)
        with self.uow() as uow:
            country = self._country(uow)
            if treatment not in profile_of(country).notice_treatments:
                raise ValidationError("treatment", "this tax treatment has no notice")
            default = profile_of(country).notice(treatment, language)
            if cleaned and cleaned != default:
                uow.legal_notices.save(treatment, language, cleaned)
            else:
                uow.legal_notices.delete(treatment, language)
            uow.commit()
            customized = bool(cleaned) and cleaned != default
            return LegalNotice(
                treatment=treatment,
                language=language,
                text=cleaned if customized else default,
                default_text=default,
                customized=customized,
            )

    # --- Helpers -----------------------------------------------------------------

    @staticmethod
    def _next_position(uow: UnitOfWork, command: SaveTextTemplate) -> int:
        positions = [
            template.position
            for template in uow.text_templates.list()
            if (template.kind, template.document_type, template.language)
            == (command.kind, command.document_type, command.language)
        ]
        return max(positions, default=-1) + 1

    @staticmethod
    def _build(template_id: UUID, command: SaveTextTemplate, position: int) -> TextTemplate:
        return TextTemplate(
            id=template_id,
            kind=command.kind,
            document_type=command.document_type,
            language=command.language,
            name=command.name,
            text=command.text,
            is_default=command.is_default,
            position=position,
        )

    @staticmethod
    def _require(uow: UnitOfWork, template_id: UUID) -> TextTemplate:
        template = uow.text_templates.get(template_id)
        if template is None:
            raise NotFoundError("text template not found")
        return template

    @staticmethod
    def _country(uow: UnitOfWork) -> Country:
        company = uow.company.get()
        if company is None:
            raise ValidationError("company", "please set up the company first")
        return company.country
