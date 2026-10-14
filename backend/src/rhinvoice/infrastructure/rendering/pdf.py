"""PDFs from the HTML page of the print template, printed by a headless Chromium.

The same Chromium that shows the preview prints the page, so the PDF looks
exactly like the preview. Fonts are embedded (static Inter weights); the PDF is
tagged for screen readers. Every PDF is made a PDF/A-3b afterwards, invoices
with their e-invoice embedded (see pdfa.py).

Which Chromium prints is a ``PagePrinter``: Gotenberg in the Docker setup, or a
browser on this computer for installations without Docker (chromium.py, ADR 0021).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import httpx

from rhinvoice.application.errors import UnavailableError
from rhinvoice.infrastructure.rendering.labels import LABELS, REMINDER_TITLES, TITLES
from rhinvoice.infrastructure.rendering.pdfa import PdfInfo, to_pdfa

if TYPE_CHECKING:
    from rhinvoice.application.document.printing import PrintModel, ReminderPrint
    from rhinvoice.domain.document.document import Document
    from rhinvoice.infrastructure.rendering.html import JinjaDocumentRenderer

CONVERT_PATH = "/forms/chromium/convert/html"
TIMEOUT_SECONDS = 30.0
# A4 in inches; the page has its own margins (see document.css).
PAGE_OPTIONS = {
    "paperWidth": "8.27",
    "paperHeight": "11.69",
    "marginTop": "0",
    "marginBottom": "0",
    "marginLeft": "0",
    "marginRight": "0",
    "printBackground": "true",
    "preferCssPageSize": "true",
    "generateTaggedPdf": "true",
}


def pdf_title(model: PrintModel) -> str:
    document = model.view.document
    language = document.content.language
    title = TITLES[language][document.type]
    if document.number is None:
        return f"{title} ({LABELS[language]['draft']})"
    return f"{title} {document.number}"


class PagePrinter(Protocol):
    def print_pdf(self, page: str) -> bytes:
        """Print a complete HTML page (A4, fonts and images inline) as a PDF."""
        ...


class ChromiumPdfRenderer:
    """The ``PdfRenderer`` port: the template's page, printed and made a PDF/A."""

    def __init__(self, html: JinjaDocumentRenderer, printer: PagePrinter) -> None:
        self._html = html
        self._printer = printer

    @property
    def printer(self) -> PagePrinter:
        return self._printer

    def pdf(self, model: PrintModel, e_invoice: bytes | None = None) -> bytes:
        document = model.view.document
        language = document.content.language
        info = PdfInfo(
            title=pdf_title(model),
            author=model.company.name,
            subject=document.content.subject,
            created=document.issued_at or document.created_at,
            keywords=(
                TITLES[language][document.type],
                document.number or "",
                "" if model.recipient is None else model.recipient.display_name,
                "" if e_invoice is None else "ZUGFeRD",
            ),
        )
        return to_pdfa(self._printer.print_pdf(self._html.html(model)), info, e_invoice)

    def reminder_pdf(self, reminder: ReminderPrint) -> bytes:
        model = reminder.model
        info = PdfInfo(
            title=reminder_title(reminder),
            author=model.company.name,
            subject=pdf_title(model),
            created=reminder.reminder.created_at,
            keywords=(
                REMINDER_TITLES[model.view.document.content.language][reminder.reminder.level],
                model.view.document.number or "",
                "" if model.recipient is None else model.recipient.display_name,
            ),
        )
        return to_pdfa(self._printer.print_pdf(self._html.reminder_html(reminder)), info)


class GotenbergPrinter:
    """The ``PagePrinter`` of the Docker setup: Gotenberg's Chromium."""

    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self._url = base_url.rstrip("/") + CONVERT_PATH
        self._client = client or httpx.Client(timeout=TIMEOUT_SECONDS)

    def print_pdf(self, page: str) -> bytes:
        try:
            response = self._client.post(
                self._url,
                files={"files": ("index.html", page.encode(), "text/html")},
                data=PAGE_OPTIONS,
            )
        except httpx.HTTPError as error:
            msg = "the PDF service (Gotenberg) is not reachable"
            raise UnavailableError(msg) from error
        if not response.is_success:
            msg = f"the PDF service (Gotenberg) failed with status {response.status_code}"
            raise UnavailableError(msg)
        # Issued documents keep their first PDF forever: only a real PDF may be archived.
        media_type = response.headers.get("content-type", "").split(";")[0].strip()
        if media_type != "application/pdf" or not response.content.startswith(b"%PDF-"):
            msg = "the PDF service (Gotenberg) did not return a PDF"
            raise UnavailableError(msg)
        return response.content


def reminder_title(reminder: ReminderPrint) -> str:
    """E.g. "1. Mahnung R20260001"."""
    document = reminder.model.view.document
    title = REMINDER_TITLES[document.content.language][reminder.reminder.level]
    return f"{title} {document.number}"


def file_name(title: str, extension: str = ".pdf") -> str:
    """Turn a title into a file name: number patterns may contain refused characters."""
    safe = "".join("-" if character in '/\\:*?"<>|' else character for character in title)
    return safe + extension


def pdf_file_name(document: Document) -> str:
    """File name for downloads, e.g. "Rechnung R20260001.pdf" or "Invoice (Draft).pdf"."""
    language = document.content.language
    title = TITLES[language][document.type]
    if document.number is None:
        name = f"{title} ({LABELS[language]['draft']})"
    else:
        name = f"{title} {document.number}"
    return file_name(name)
