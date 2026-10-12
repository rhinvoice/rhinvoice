"""What sending mails needs from the outside: the server, the files, the templates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from rhinvoice.application.document.handlers import DocumentView
    from rhinvoice.domain.dunning.reminder import Reminder
    from rhinvoice.domain.mail.server import MailServer
    from rhinvoice.domain.mail.template import MailKind, MailTemplate
    from rhinvoice.domain.shared.email import EmailAddress
    from rhinvoice.domain.shared.language import Language
    from rhinvoice.domain.text.template import Placeholder


@dataclass(frozen=True, slots=True)
class Attachment:
    name: str
    content: bytes
    media_type: str


@dataclass(frozen=True, slots=True)
class OutgoingMail:
    to: tuple[EmailAddress, ...]
    subject: str
    body: str
    attachments: tuple[Attachment, ...] = ()
    bcc: tuple[EmailAddress, ...] = ()
    """Blind copies, e.g. to the sender as a record."""


@dataclass(frozen=True, slots=True)
class MailValues:
    """What a template is filled with, and the name of the file the mail carries."""

    placeholders: Mapping[Placeholder, str]
    file_name: str


class MailSender(Protocol):
    def send(self, server: MailServer, mail: OutgoingMail) -> tuple[str, ...]:
        """Hand the mail to the server; return the recipients it refused (the others got it).

        Raise DeliveryError when nothing went out.
        """
        ...


class MailContent(Protocol):
    """The printed side of a mail: the placeholder values and the attached files."""

    def document_values(self, view: DocumentView) -> MailValues: ...

    def document_files(self, document_id: UUID, *, xrechnung: bool) -> tuple[Attachment, ...]:
        """Return the PDF (archived for issued documents), and the XRechnung on request."""
        ...

    def reminder_values(self, reminder: Reminder) -> MailValues: ...
    def reminder_files(self, reminder: Reminder) -> tuple[Attachment, ...]: ...


class MailRepository(Protocol):
    def server(self) -> MailServer | None: ...
    def save_server(self, server: MailServer) -> None: ...
    def templates(self) -> dict[tuple[MailKind, Language], MailTemplate]:
        """Return the company's own templates; built-in ones are not stored."""
        ...

    def save_template(self, template: MailTemplate) -> None: ...
    def delete_template(self, kind: MailKind, language: Language) -> None: ...
