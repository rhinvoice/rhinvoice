"""Use cases of sending documents and reminders by mail (see ADR 0015)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from rhinvoice.application.errors import DeliveryError, NotFoundError, UnavailableError
from rhinvoice.application.mail.ports import OutgoingMail
from rhinvoice.domain.document.document import (
    MAX_EVENT_DETAIL,
    OPEN_INVOICE_STATUSES,
    DocumentType,
    EventKind,
)
from rhinvoice.domain.mail.message import recipients
from rhinvoice.domain.mail.server import MailSecurity, MailServer
from rhinvoice.domain.mail.template import (
    MAX_BODY,
    MAX_SUBJECT,
    MailKind,
    MailTemplate,
    default_template,
)
from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.text import clean_multiline, clean_text
from rhinvoice.domain.text.template import fill_placeholders

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from rhinvoice.application.document.handlers import DocumentHandlers, DocumentView
    from rhinvoice.application.mail.ports import (
        MailContent,
        MailSender,
        MailValues,
    )
    from rhinvoice.application.uow import UnitOfWork, UnitOfWorkFactory
    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.dunning.reminder import Reminder
    from rhinvoice.domain.shared.clock import Clock


@dataclass(frozen=True, slots=True)
class SaveMailServer:
    host: str
    port: int
    security: MailSecurity
    sender: str
    sender_name: str = ""
    username: str = ""
    password: str | None = None
    """None keeps the stored password; "" removes it."""
    reply_to: str = ""
    copy_to_sender: bool = True


@dataclass(frozen=True, slots=True)
class MailServerView:
    server: MailServer | None
    """The server without its password; None while none is set up."""
    password_set: bool


@dataclass(frozen=True, slots=True)
class MailTemplateView:
    template: MailTemplate
    default: MailTemplate
    customized: bool


@dataclass(frozen=True, slots=True)
class MailDraft:
    """A mail ready to send, for the person to check and change."""

    to: tuple[str, ...]
    subject: str
    body: str
    attachment: str
    """The name of the attached PDF."""
    copy_to: str | None
    """The sender address that gets a blind copy, if the server is set up so."""


@dataclass(frozen=True, slots=True)
class SendMail:
    to: tuple[str, ...]
    subject: str
    body: str
    xrechnung: bool = False
    """Attach the XRechnung too (invoices and cancellations only)."""


@dataclass(frozen=True, slots=True)
class MailHandlers:
    uow: UnitOfWorkFactory
    clock: Clock
    documents: DocumentHandlers
    content: MailContent
    sender: MailSender

    # --- Server -------------------------------------------------------------------

    def server(self) -> MailServerView:
        with self.uow() as uow:
            server = uow.mail.server()
        if server is None:
            return MailServerView(server=None, password_set=False)
        return MailServerView(
            server=replace(server, password=""), password_set=bool(server.password)
        )

    def save_server(self, command: SaveMailServer) -> MailServerView:
        with self.uow() as uow:
            stored = uow.mail.server()
            if not command.username.strip():
                password = ""  # without a user name there is no login, and nothing to keep
            elif command.password is None:
                password = _kept_password(stored, command)
            else:
                password = command.password
            server = MailServer(
                host=command.host,
                port=command.port,
                security=command.security,
                sender=_address(command.sender, "sender"),
                sender_name=command.sender_name,
                username=command.username,
                password=password,
                reply_to=_address(command.reply_to, "reply_to")
                if command.reply_to.strip()
                else None,
                copy_to_sender=command.copy_to_sender,
            )
            uow.mail.save_server(server)
            uow.commit()
        return self.server()

    def send_test(self, to: str) -> None:
        """Send a short mail to check the settings; nothing is recorded."""
        with self.uow() as uow:
            server = _require_server(uow)
            language = _company(uow).default_language
        subject, body = _TEST[language]
        self.sender.send(server, OutgoingMail(to=recipients([to]), subject=subject, body=body))

    # --- Templates ----------------------------------------------------------------

    def templates(self) -> list[MailTemplateView]:
        with self.uow() as uow:
            company = _company(uow)
            own = uow.mail.templates()
        views: list[MailTemplateView] = []
        for kind in MailKind:
            for language in Language:
                default = default_template(kind, language, company.country)
                template = own.get((kind, language))
                views.append(
                    MailTemplateView(
                        template=default if template is None else template,
                        default=default,
                        customized=template is not None,
                    )
                )
        return views

    def save_template(
        self, kind: MailKind, language: Language, subject: str, body: str
    ) -> MailTemplateView:
        """Keep the company's own wording; the built-in one (or an empty text) restores it."""
        with self.uow() as uow:
            default = default_template(kind, language, _company(uow).country)
            if not subject.strip() and not body.strip():
                template = default
            else:
                template = MailTemplate(kind, language, subject, body)
            customized = (template.subject, template.body) != (default.subject, default.body)
            if customized:
                uow.mail.save_template(template)
            else:
                uow.mail.delete_template(kind, language)
            uow.commit()
        return MailTemplateView(
            template=template if customized else default, default=default, customized=customized
        )

    # --- Documents ------------------------------------------------------------------

    def document_draft(self, document_id: UUID) -> MailDraft:
        """Prepare the mail of an issued document to its customer."""
        view = self._sendable(document_id)
        kind = MailKind.of_document(view.document.type)
        values = self.content.document_values(view)
        return self._draft(view, kind, values)

    def send_document(self, document_id: UUID, command: SendMail) -> DocumentView:
        """Send an issued document with its PDF and note it in the document's history."""
        view = self._sendable(document_id)
        if command.xrechnung and view.document.type is DocumentType.QUOTE:
            raise ValidationError("xrechnung", "quotes are no e-invoices")
        to = recipients(command.to)
        mail = _mail(to, command)
        with self.uow() as uow:
            server = _require_server(uow)
        files = self.content.document_files(document_id, xrechnung=command.xrechnung)
        accepted, refused = self._send(server, replace(mail, attachments=files))
        view = self._record(document_id, EventKind.EMAILED, _names(accepted, MAX_EVENT_DETAIL))
        _report_refused(refused)
        return view

    # --- Reminders ------------------------------------------------------------------

    def reminder_draft(self, reminder_id: UUID) -> MailDraft:
        reminder = self._reminder(reminder_id)
        view = self._open_invoice(reminder)
        values = self.content.reminder_values(reminder)
        return self._draft(view, MailKind.of_reminder(reminder.level), values)

    def send_reminder(self, reminder_id: UUID, command: SendMail) -> DocumentView:
        """Send a reminder with its letter and note it in the invoice's history."""
        reminder = self._reminder(reminder_id)
        self._open_invoice(reminder)
        to = recipients(command.to)
        mail = _mail(to, command)
        with self.uow() as uow:
            server = _require_server(uow)
        letter = self.content.reminder_files(reminder)
        accepted, refused = self._send(server, replace(mail, attachments=letter))
        view = self._record(
            reminder.invoice_id,
            EventKind.REMINDER_EMAILED,
            f"{reminder.level} {_names(accepted, MAX_EVENT_DETAIL - 2)}",
        )
        _report_refused(refused)
        return view

    # --- Helpers --------------------------------------------------------------------

    def _sendable(self, document_id: UUID) -> DocumentView:
        view = self.documents.get(document_id)
        if view.document.is_draft:
            raise ValidationError(
                "document", "drafts are not sent; issue the document first", code="mail_draft"
            )
        return view

    def _open_invoice(self, reminder: Reminder) -> DocumentView:
        """Reminders only go out while their invoice is still open (not paid, not cancelled)."""
        view = self.documents.get(reminder.invoice_id)
        if view.document.status not in OPEN_INVOICE_STATUSES:
            raise InvalidStateError(
                "the invoice is no longer open; its reminders are not sent",
                code="reminder_not_open",
            )
        return view

    def _reminder(self, reminder_id: UUID) -> Reminder:
        with self.uow() as uow:
            reminder = uow.dunning.get(reminder_id)
        if reminder is None:
            raise NotFoundError("reminder not found")
        return reminder

    def _draft(self, view: DocumentView, kind: MailKind, values: MailValues) -> MailDraft:
        language = view.document.content.language
        with self.uow() as uow:
            server = uow.mail.server()
            template = uow.mail.templates().get((kind, language)) or default_template(
                kind, language, _company(uow).country
            )
        customer = view.customer
        email = None if customer is None else customer.email
        return MailDraft(
            to=() if email is None else (str(email),),
            subject=fill_placeholders(template.subject, values.placeholders),
            body=fill_placeholders(template.body, values.placeholders),
            attachment=values.file_name,
            copy_to=str(server.sender) if server is not None and server.copy_to_sender else None,
        )

    def _send(
        self, server: MailServer, mail: OutgoingMail
    ) -> tuple[tuple[EmailAddress, ...], tuple[EmailAddress, ...]]:
        """Send; return the recipients that got the mail and those the server refused.

        Only the blind copy refused: the customer got the mail, nothing to report.
        """
        copy = (server.sender,) if server.copy_to_sender and server.sender not in mail.to else ()
        refused = set(self.sender.send(server, replace(mail, bcc=copy)))
        accepted = tuple(address for address in mail.to if str(address) not in refused)
        not_reached = tuple(address for address in mail.to if str(address) in refused)
        if not accepted:
            raise DeliveryError(
                f"the server refused the recipient {_names(not_reached)}",
                code="mail_recipient_refused",
            )
        return accepted, not_reached

    def _record(self, document_id: UUID, kind: EventKind, detail: str) -> DocumentView:
        with self.uow() as uow:
            document = uow.documents.get(document_id, for_update=True)
            if document is None:
                raise NotFoundError("document not found")
            view = self.documents.save_in(uow, document.record_mail(kind, detail, self.clock.now()))
            uow.commit()
        return view


_TEST = {
    Language.DE: (
        "Rhinvoice: Test-E-Mail",
        "Diese E-Mail bestätigt, dass Rhinvoice über den eingerichteten Server senden kann.",
    ),
    Language.EN: (
        "Rhinvoice: test mail",
        "This mail confirms that Rhinvoice can send through the configured server.",
    ),
    Language.FR: (
        "Rhinvoice : e-mail de test",
        "Cet e-mail confirme que Rhinvoice peut envoyer par le serveur configuré.",
    ),
    Language.IT: (
        "Rhinvoice: e-mail di prova",
        "Questa e-mail conferma che Rhinvoice può inviare tramite il server configurato.",
    ),
}


def _mail(to: tuple[EmailAddress, ...], command: SendMail) -> OutgoingMail:
    subject = clean_text(command.subject, "subject", max_length=MAX_SUBJECT, required=True)
    body = clean_multiline(command.body, "body", max_length=MAX_BODY)
    if not body:
        raise ValidationError("body", "body is required")
    return OutgoingMail(to=to, subject=subject, body=body)


def _names(addresses: Sequence[EmailAddress], limit: int = MAX_EVENT_DETAIL) -> str:
    """List the addresses for the history, whole ones only, in at most ``limit`` characters."""
    shown: list[str] = []
    for index, address in enumerate(addresses):
        rest = len(addresses) - index
        candidate = ", ".join([*shown, str(address)])
        more = f" (+{rest - 1})" if rest > 1 else ""
        if len(candidate) + len(more) > limit:
            return f"{', '.join(shown)} (+{rest})"
        shown.append(str(address))
    return ", ".join(shown)


def _report_refused(refused: Sequence[EmailAddress]) -> None:
    """Tell the person who did not get a mail that the others received (and was noted)."""
    if refused:
        raise DeliveryError(
            f"the server refused {_names(refused)}; the other recipients received the mail",
            code="mail_partly_refused",
            details={"refused": _names(refused)},
        )


def _kept_password(stored: MailServer | None, command: SaveMailServer) -> str:
    """Keep the stored password only for the same server, port and user.

    Otherwise a changed host could receive the stored password at the next login.
    """
    if stored is None or not stored.password:
        return ""
    same = (stored.host, stored.port, stored.username) == (
        command.host.strip(),
        command.port,
        command.username.strip(),
    )
    if not same:
        raise ValidationError(
            "password",
            "enter the password again for the changed server or user",
            code="mail_password_required",
        )
    return stored.password


def _address(raw: str, field: str) -> EmailAddress:
    try:
        return EmailAddress.parse(raw)
    except ValidationError as error:
        raise ValidationError(field, error.message) from None


def _require_server(uow: UnitOfWork) -> MailServer:
    server = uow.mail.server()
    if server is None:
        raise UnavailableError(
            "set up the mail server first (Settings → E-mail)", code="mail_not_configured"
        )
    return server


def _company(uow: UnitOfWork) -> Company:
    company = uow.company.get()
    if company is None:
        raise ValidationError("company", "please set up the company first")
    return company
