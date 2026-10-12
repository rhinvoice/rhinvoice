"""Sending documents and reminders by mail, and the mail settings (ADR 0015)."""

from typing import Annotated, Self
from uuid import UUID

from fastapi import APIRouter, status
from pydantic import Field

from rhinvoice.api.dependencies import NOT_IN_DEMO, ContainerDep, CurrentUser
from rhinvoice.api.routers.documents import DocumentResponse
from rhinvoice.api.schemas import ERROR_RESPONSES, ApiModel, ErrorResponse, text
from rhinvoice.application.mail.handlers import (
    MailDraft,
    MailServerView,
    MailTemplateView,
    SaveMailServer,
    SendMail,
)
from rhinvoice.domain.mail.message import MAX_RECIPIENTS
from rhinvoice.domain.mail.server import (
    MAX_HOST,
    MAX_PASSWORD,
    MAX_PORT,
    MAX_SENDER_NAME,
    MAX_USERNAME,
    MIN_PORT,
    MailSecurity,
)
from rhinvoice.domain.mail.template import MAX_BODY, MAX_SUBJECT, MailKind
from rhinvoice.domain.shared.email import MAX_EMAIL_LENGTH
from rhinvoice.domain.shared.language import Language

router = APIRouter(prefix="/api", tags=["mail"], responses=ERROR_RESPONSES)

SENDING: dict[int | str, dict[str, object]] = {
    502: {"model": ErrorResponse, "description": "The mail server refused or did not answer"},
    503: {"model": ErrorResponse, "description": "No mail server is set up"},
}
Address = Annotated[str, Field(max_length=MAX_EMAIL_LENGTH)]


class MailServerRequest(ApiModel):
    host: str = Field(min_length=1, max_length=MAX_HOST)
    port: int = Field(ge=MIN_PORT, le=MAX_PORT)
    security: MailSecurity
    sender: Address
    sender_name: str = text(MAX_SENDER_NAME)
    username: str = text(MAX_USERNAME)
    password: str | None = Field(default=None, max_length=MAX_PASSWORD)
    """None keeps the stored password, "" removes it."""
    reply_to: str = Field(default="", max_length=MAX_EMAIL_LENGTH)
    copy_to_sender: bool = True

    def to_command(self) -> SaveMailServer:
        return SaveMailServer(
            host=self.host,
            port=self.port,
            security=self.security,
            sender=self.sender,
            sender_name=self.sender_name,
            username=self.username,
            password=self.password,
            reply_to=self.reply_to,
            copy_to_sender=self.copy_to_sender,
        )


class MailServerResponse(ApiModel):
    configured: bool
    host: str
    port: int
    security: MailSecurity
    sender: str
    sender_name: str
    username: str
    password_set: bool
    """The password itself never leaves the server."""
    reply_to: str
    copy_to_sender: bool

    @classmethod
    def of(cls, view: MailServerView) -> Self:
        server = view.server
        if server is None:
            return cls(
                configured=False,
                host="",
                port=MailSecurity.STARTTLS.default_port,
                security=MailSecurity.STARTTLS,
                sender="",
                sender_name="",
                username="",
                password_set=False,
                reply_to="",
                copy_to_sender=True,
            )
        return cls(
            configured=True,
            host=server.host,
            port=server.port,
            security=server.security,
            sender=str(server.sender),
            sender_name=server.sender_name,
            username=server.username,
            password_set=view.password_set,
            reply_to="" if server.reply_to is None else str(server.reply_to),
            copy_to_sender=server.copy_to_sender,
        )


class TestMailRequest(ApiModel):
    to: Address


class MailTemplateRequest(ApiModel):
    subject: str = Field(max_length=MAX_SUBJECT)
    body: str = Field(max_length=MAX_BODY)


class MailTemplateResponse(ApiModel):
    kind: MailKind
    language: Language
    subject: str
    body: str
    default_subject: str
    default_body: str
    customized: bool

    @classmethod
    def of(cls, view: MailTemplateView) -> Self:
        return cls(
            kind=view.template.kind,
            language=view.template.language,
            subject=view.template.subject,
            body=view.template.body,
            default_subject=view.default.subject,
            default_body=view.default.body,
            customized=view.customized,
        )


class MailDraftResponse(ApiModel):
    to: list[str]
    subject: str
    body: str
    attachment: str
    """The name of the attached PDF."""
    copy_to: str | None
    """The sender address that gets a blind copy, if any."""

    @classmethod
    def of(cls, draft: MailDraft) -> Self:
        return cls(
            to=list(draft.to),
            subject=draft.subject,
            body=draft.body,
            attachment=draft.attachment,
            copy_to=draft.copy_to,
        )


class SendMailRequest(ApiModel):
    to: list[Address] = Field(min_length=1, max_length=MAX_RECIPIENTS)
    subject: str = Field(max_length=MAX_SUBJECT)
    body: str = Field(max_length=MAX_BODY)
    xrechnung: bool = False
    """Attach the XRechnung as well (invoices and cancellations)."""

    def to_command(self) -> SendMail:
        return SendMail(
            to=tuple(self.to), subject=self.subject, body=self.body, xrechnung=self.xrechnung
        )


@router.get("/mail/server")
def mail_server(_user: CurrentUser, container: ContainerDep) -> MailServerResponse:
    return MailServerResponse.of(container.mail.server())


@router.put("/mail/server", dependencies=[NOT_IN_DEMO])
def save_mail_server(
    body: MailServerRequest, _user: CurrentUser, container: ContainerDep
) -> MailServerResponse:
    return MailServerResponse.of(container.mail.save_server(body.to_command()))


@router.post(
    "/mail/test",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=SENDING,
    dependencies=[NOT_IN_DEMO],
)
def send_test_mail(body: TestMailRequest, _user: CurrentUser, container: ContainerDep) -> None:
    """Send a short mail through the server to check the settings."""
    container.mail.send_test(body.to)


@router.get("/mail/templates")
def mail_templates(_user: CurrentUser, container: ContainerDep) -> list[MailTemplateResponse]:
    return [MailTemplateResponse.of(view) for view in container.mail.templates()]


@router.put("/mail/templates/{kind}/{language}")
def save_mail_template(
    kind: MailKind,
    language: Language,
    body: MailTemplateRequest,
    _user: CurrentUser,
    container: ContainerDep,
) -> MailTemplateResponse:
    """Use the company's own wording; the built-in one (or empty texts) restores it."""
    view = container.mail.save_template(kind, language, body.subject, body.body)
    return MailTemplateResponse.of(view)


@router.get("/documents/{document_id}/mail")
def document_mail(
    document_id: UUID, _user: CurrentUser, container: ContainerDep
) -> MailDraftResponse:
    """Prepare the mail of an issued document to its customer, to check and send."""
    return MailDraftResponse.of(container.mail.document_draft(document_id))


@router.post("/documents/{document_id}/mail", responses=SENDING, dependencies=[NOT_IN_DEMO])
def send_document_mail(
    document_id: UUID, body: SendMailRequest, _user: CurrentUser, container: ContainerDep
) -> DocumentResponse:
    """Send the document's PDF (and XRechnung) and note it in its history."""
    return DocumentResponse.of(container.mail.send_document(document_id, body.to_command()))


@router.get("/reminders/{reminder_id}/mail")
def reminder_mail(
    reminder_id: UUID, _user: CurrentUser, container: ContainerDep
) -> MailDraftResponse:
    return MailDraftResponse.of(container.mail.reminder_draft(reminder_id))


@router.post("/reminders/{reminder_id}/mail", responses=SENDING, dependencies=[NOT_IN_DEMO])
def send_reminder_mail(
    reminder_id: UUID, body: SendMailRequest, _user: CurrentUser, container: ContainerDep
) -> DocumentResponse:
    """Send the reminder letter; the invoice's history notes it."""
    return DocumentResponse.of(container.mail.send_reminder(reminder_id, body.to_command()))
