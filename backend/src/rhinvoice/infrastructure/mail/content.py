"""The printed side of mails: placeholder values in the document's format, the files."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rhinvoice.application.mail.ports import Attachment, MailValues
from rhinvoice.infrastructure.rendering.html import placeholder_values, reminder_placeholder_values
from rhinvoice.infrastructure.rendering.pdf import file_name, pdf_file_name, reminder_title

if TYPE_CHECKING:
    from uuid import UUID

    from rhinvoice.application.document.handlers import DocumentView
    from rhinvoice.application.document.printing import PrintHandlers
    from rhinvoice.domain.dunning.reminder import Reminder

PDF = "application/pdf"
XML = "application/xml"


class PrintedMailContent:
    """The mail content of the application (see MailContent), from the print handlers."""

    def __init__(self, printing: PrintHandlers) -> None:
        self._printing = printing

    def document_values(self, view: DocumentView) -> MailValues:
        model = self._printing.model(view)
        return MailValues(placeholder_values(model), pdf_file_name(view.document))

    def document_files(self, document_id: UUID, *, xrechnung: bool) -> tuple[Attachment, ...]:
        pdf = self._printing.pdf(document_id)
        files = [Attachment(pdf_file_name(pdf.document), pdf.content, PDF)]
        if xrechnung:
            document, xml = self._printing.xrechnung(document_id)
            files.append(
                Attachment(file_name(f"XRechnung {document.issued_number}", ".xml"), xml, XML)
            )
        return tuple(files)

    def reminder_values(self, reminder: Reminder) -> MailValues:
        printed = self._printing.reminder(reminder.id)
        return MailValues(reminder_placeholder_values(printed), file_name(reminder_title(printed)))

    def reminder_files(self, reminder: Reminder) -> tuple[Attachment, ...]:
        printed, pdf = self._printing.reminder_pdf(reminder.id)
        return (Attachment(file_name(reminder_title(printed)), pdf, PDF),)
