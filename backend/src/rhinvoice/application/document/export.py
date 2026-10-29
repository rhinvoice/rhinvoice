"""Export the issued invoices of a period for the bookkeeping or the tax adviser (ADR 0038).

The list comes as Excel, CSV or PDF; with ``with_pdfs`` a ZIP holds the list and the
PDF of every document, named as the list's column "file" says. Own documents add their
archived PDF (archived now if it was not yet) and the files attached to them (ADR 0040),
imported invoices their original.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import StrEnum
from io import BytesIO
from typing import TYPE_CHECKING, Protocol

from rhinvoice.application.errors import ConflictError
from rhinvoice.domain.document.export import ExportListing, export_listing

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from typing import IO

    from rhinvoice.application.document.printing import PrintHandlers
    from rhinvoice.application.uow import UnitOfWorkFactory
    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.document.export import ExportPeriod
    from rhinvoice.domain.shared.clock import Clock
    from rhinvoice.domain.shared.language import Language


class ExportFormat(StrEnum):
    XLSX = "xlsx"
    CSV = "csv"
    PDF = "pdf"

    @property
    def media_type(self) -> str:
        return {
            ExportFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ExportFormat.CSV: "text/csv; charset=utf-8",
            ExportFormat.PDF: "application/pdf",
        }[self]


ZIP_MEDIA_TYPE = "application/zip"


@dataclass(frozen=True, slots=True)
class ExportRequest:
    period: ExportPeriod
    format: ExportFormat
    with_pdfs: bool = False
    """Add the PDF of every document: the list and the PDFs come as a ZIP."""
    language: Language | None = None
    """Of the column headers; None: the company's default language."""


@dataclass(frozen=True, slots=True)
class ExportFile:
    name: str
    media_type: str
    content: IO[bytes]
    """Read from the start; the caller closes it."""


class ExportWriter(Protocol):
    def title(self, language: Language) -> str:
        """Name the list in file names, e.g. "Rechnungen"."""
        ...

    def write(
        self,
        listing: ExportListing,
        company: Company,
        export_format: ExportFormat,
        language: Language,
    ) -> bytes:
        """Write the list as a spreadsheet, CSV or PDF."""
        ...

    def archive(self, files: Iterable[tuple[str, bytes]]) -> IO[bytes]:
        """Pack the files into a ZIP, one at a time, and return it read from the start."""
        ...


@dataclass(frozen=True, slots=True)
class ExportHandlers:
    uow: UnitOfWorkFactory
    clock: Clock
    printing: PrintHandlers
    writer: ExportWriter
    running: threading.Lock = field(default_factory=threading.Lock, compare=False)
    """One export at a time: one with PDFs may render many of them (ADR 0038)."""

    def export(self, request: ExportRequest) -> ExportFile:
        if not self.running.acquire(blocking=False):
            raise ConflictError("another export is being prepared", code="export_busy")
        try:
            return self._export(request)
        finally:
            self.running.release()

    def _export(self, request: ExportRequest) -> ExportFile:
        period = request.period
        with self.uow() as uow:
            company = uow.company.get()
            documents = uow.documents.issued_between(period.start, period.end)
            attachments = (
                {document.id: uow.documents.attachments(document.id) for document in documents}
                if request.with_pdfs
                else {}
            )
        if company is None:
            raise ConflictError("set up the company before exporting", code="company_not_set_up")
        language = request.language or company.default_language
        name = f"{self.writer.title(language)} {period.label}"
        list_name = f"{name}.{request.format.value}"
        listing = export_listing(
            period,
            documents,
            self.clock.today(),
            with_files=request.with_pdfs,
            reserved=(list_name,),
            attachments=attachments,
        )
        content = self.writer.write(listing, company, request.format, language)
        if not request.with_pdfs:
            return ExportFile(list_name, request.format.media_type, BytesIO(content))
        archive = self.writer.archive(self._files(list_name, content, listing))
        return ExportFile(f"{name}.zip", ZIP_MEDIA_TYPE, archive)

    def _files(
        self, list_name: str, content: bytes, listing: ExportListing
    ) -> Iterator[tuple[str, bytes]]:
        """Yield the list, then each PDF and its attachments: one file in memory at a time."""
        yield list_name, content
        for row in listing.rows:
            if row.file_name is not None:
                yield row.file_name, self.printing.pdf(row.document_id).content
            for attachment_id, name in row.attachment_files:
                with self.uow() as uow:
                    found = uow.documents.get_attachment(row.document_id, attachment_id)
                if found is not None:
                    yield name, found[1]
