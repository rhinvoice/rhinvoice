from typing import Self
from uuid import UUID

from fastapi import APIRouter, status
from pydantic import Field

from rhinvoice.api.dependencies import ContainerDep, CurrentUser
from rhinvoice.api.schemas import ERROR_RESPONSES, ApiModel
from rhinvoice.application.text.handlers import LegalNotice, SaveTextTemplate
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.tax.treatment import TaxTreatment
from rhinvoice.domain.text.notice import MAX_NOTICE
from rhinvoice.domain.text.template import MAX_NAME, MAX_TEMPLATE_TEXT, TextKind, TextTemplate

router = APIRouter(prefix="/api", tags=["texts"], responses=ERROR_RESPONSES)


class TextTemplateRequest(ApiModel):
    kind: TextKind
    document_type: DocumentType
    language: Language
    name: str = Field(min_length=1, max_length=MAX_NAME)
    text: str = Field(min_length=1, max_length=MAX_TEMPLATE_TEXT)
    is_default: bool = False

    def to_command(self) -> SaveTextTemplate:
        return SaveTextTemplate(
            kind=self.kind,
            document_type=self.document_type,
            language=self.language,
            name=self.name,
            text=self.text,
            is_default=self.is_default,
        )


class TextTemplateResponse(ApiModel):
    id: UUID
    kind: TextKind
    document_type: DocumentType
    language: Language
    name: str
    text: str
    is_default: bool
    position: int

    @classmethod
    def of(cls, template: TextTemplate) -> Self:
        return cls(
            id=template.id,
            kind=template.kind,
            document_type=template.document_type,
            language=template.language,
            name=template.name,
            text=template.text,
            is_default=template.is_default,
            position=template.position,
        )


class MoveRequest(ApiModel):
    up: bool
    """True: one place up (earlier on the document), false: one place down."""


class LegalNoticeRequest(ApiModel):
    text: str = Field(max_length=MAX_NOTICE)
    """Empty: use the built-in wording again."""


class LegalNoticeResponse(ApiModel):
    treatment: TaxTreatment
    language: Language
    text: str
    default_text: str
    customized: bool

    @classmethod
    def of(cls, notice: LegalNotice) -> Self:
        return cls(
            treatment=notice.treatment,
            language=notice.language,
            text=notice.text,
            default_text=notice.default_text,
            customized=notice.customized,
        )


@router.get("/text-templates")
def list_text_templates(_user: CurrentUser, container: ContainerDep) -> list[TextTemplateResponse]:
    return [TextTemplateResponse.of(item) for item in container.texts.list_templates()]


@router.post("/text-templates", status_code=status.HTTP_201_CREATED)
def create_text_template(
    body: TextTemplateRequest, _user: CurrentUser, container: ContainerDep
) -> TextTemplateResponse:
    return TextTemplateResponse.of(container.texts.create_template(body.to_command()))


@router.put("/text-templates/{template_id}")
def update_text_template(
    template_id: UUID, body: TextTemplateRequest, _user: CurrentUser, container: ContainerDep
) -> TextTemplateResponse:
    return TextTemplateResponse.of(container.texts.update_template(template_id, body.to_command()))


@router.post("/text-templates/{template_id}/move")
def move_text_template(
    template_id: UUID, body: MoveRequest, _user: CurrentUser, container: ContainerDep
) -> list[TextTemplateResponse]:
    """Swap the template with its neighbour; returns all templates in their new order."""
    moved = container.texts.move_template(template_id, up=body.up)
    return [TextTemplateResponse.of(item) for item in moved]


@router.delete("/text-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_text_template(template_id: UUID, _user: CurrentUser, container: ContainerDep) -> None:
    container.texts.delete_template(template_id)


@router.get("/legal-notices")
def list_legal_notices(_user: CurrentUser, container: ContainerDep) -> list[LegalNoticeResponse]:
    """Notices per tax treatment and language, in the wording for the company's country."""
    return [LegalNoticeResponse.of(item) for item in container.texts.list_notices()]


@router.put("/legal-notices/{treatment}/{language}")
def save_legal_notice(
    treatment: TaxTreatment,
    language: Language,
    body: LegalNoticeRequest,
    _user: CurrentUser,
    container: ContainerDep,
) -> LegalNoticeResponse:
    return LegalNoticeResponse.of(container.texts.save_notice(treatment, language, body.text))
