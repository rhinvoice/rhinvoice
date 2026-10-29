"""Exporting the issued invoices of a period: the list, its name and the ZIP with the PDFs."""

import io
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import date
from typing import IO
from uuid import UUID

import pytest

from rhinvoice.application.document.export import (
    ZIP_MEDIA_TYPE,
    ExportFormat,
    ExportHandlers,
    ExportRequest,
)
from rhinvoice.application.document.handlers import (
    DocumentHandlers,
    DraftInput,
    LineInput,
    build_index,
)
from rhinvoice.application.document.printing import PrintHandlers
from rhinvoice.application.errors import ConflictError
from rhinvoice.domain.company.company import Company
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.export import ExportListing, ExportPeriod
from rhinvoice.domain.document.lines import LineKind
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.language import Language
from tests.helpers import raises_exactly
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store, StoredDocument
from tests.unit.application.test_printing import RecordingPdf, RecordingRenderer
from tests.unit.domain import factories
from tests.unit.domain.test_imported_document import imported

TODAY = NOW.date()
MARCH = ExportPeriod.month(2026, 3)
CUSTOMER = UUID(int=1)
HOURS = LineInput(kind=LineKind.ITEM, description="Beratung", quantity="2", unit_price="150")


@dataclass
class RecordingWriter:
    lists: list[tuple[ExportListing, Company, ExportFormat, Language]] = field(
        default_factory=list[tuple[ExportListing, Company, ExportFormat, Language]]
    )
    archived: list[list[tuple[str, bytes]]] = field(default_factory=list[list[tuple[str, bytes]]])

    def title(self, language: Language) -> str:
        return f"Rechnungen-{language.value}"

    def write(
        self,
        listing: ExportListing,
        company: Company,
        export_format: ExportFormat,
        language: Language,
    ) -> bytes:
        self.lists.append((listing, company, export_format, language))
        return f"list {export_format.value}".encode()

    def archive(self, files: Iterable[tuple[str, bytes]]) -> IO[bytes]:
        packed = list(files)
        self.archived.append(packed)
        return io.BytesIO(b"PK zip")


@pytest.fixture
def writer() -> RecordingWriter:
    return RecordingWriter()


@pytest.fixture
def pdfs() -> RecordingPdf:
    return RecordingPdf()


@pytest.fixture
def documents(store: Store, clock: FixedClock) -> DocumentHandlers:
    store.company = factories.company(default_language=Language.FR)
    account = factories.bank_account(is_default=True)
    store.bank_accounts[account.id] = account
    store.customers[CUSTOMER] = factories.customer(id=CUSTOMER)
    return DocumentHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)


@pytest.fixture
def exports(
    store: Store,
    clock: FixedClock,
    documents: DocumentHandlers,
    writer: RecordingWriter,
    pdfs: RecordingPdf,
) -> ExportHandlers:
    printing = PrintHandlers(
        uow=lambda: InMemoryUnitOfWork(store),
        clock=clock,
        documents=documents,
        renderer=RecordingRenderer(),
        pdf_renderer=pdfs,
    )
    return ExportHandlers(
        uow=lambda: InMemoryUnitOfWork(store), clock=clock, printing=printing, writer=writer
    )


def invoice(documents: DocumentHandlers, issue_date: date = TODAY) -> UUID:
    draft = documents.create(
        DocumentType.INVOICE,
        DraftInput(customer_id=CUSTOMER, lines=(HOURS,), issue_date=issue_date),
    )
    return documents.issue(draft.document.id).document.id


def add_imported(store: Store, *, with_pdf: bool) -> UUID:
    document = imported(issue_date=date(2026, 3, 2), due_date=date(2026, 3, 2))
    if with_pdf:
        document = document.archive_pdf("a" * 64)
        store.pdfs[document.id] = b"%PDF original"
    totals = document.frozen_totals
    store.documents[document.id] = StoredDocument(document, build_index(document, totals, None))
    return document.id


def test_the_list_holds_the_period_in_the_chosen_format_and_language(
    exports: ExportHandlers, documents: DocumentHandlers, writer: RecordingWriter, store: Store
) -> None:
    invoice(documents, date(2026, 2, 27))
    first = invoice(documents)
    documents.create(DocumentType.INVOICE, DraftInput(customer_id=CUSTOMER, lines=(HOURS,)))
    exported = exports.export(ExportRequest(MARCH, ExportFormat.CSV, language=Language.IT))
    assert exported.name == "Rechnungen-it 2026-03.csv"
    assert exported.media_type == "text/csv; charset=utf-8"
    assert exported.content.read() == b"list csv"
    [(listing, company, export_format, language)] = writer.lists
    assert [row.document_id for row in listing.rows] == [first]
    assert listing.period == MARCH
    assert not listing.with_files
    assert listing.rows[0].file_name is None
    assert company == store.company
    assert export_format is ExportFormat.CSV
    assert language is Language.IT
    assert writer.archived == []


def test_the_headers_are_in_the_company_language_by_default(
    exports: ExportHandlers, writer: RecordingWriter
) -> None:
    exported = exports.export(ExportRequest(MARCH, ExportFormat.XLSX))
    assert exported.name == "Rechnungen-fr 2026-03.xlsx"
    assert exported.media_type == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert writer.lists[0][3] is Language.FR
    assert writer.lists[0][0].rows == ()
    pdf = exports.export(ExportRequest(MARCH, ExportFormat.PDF))
    assert (pdf.name, pdf.media_type) == ("Rechnungen-fr 2026-03.pdf", "application/pdf")


def test_with_pdfs_a_zip_holds_the_list_and_every_pdf(
    exports: ExportHandlers,
    documents: DocumentHandlers,
    writer: RecordingWriter,
    store: Store,
    pdfs: RecordingPdf,
) -> None:
    own = invoice(documents)
    original = add_imported(store, with_pdf=True)
    add_imported(store, with_pdf=False)
    exported = exports.export(ExportRequest(MARCH, ExportFormat.XLSX, with_pdfs=True))
    assert exported.name == "Rechnungen-fr 2026-03.zip"
    assert exported.media_type == ZIP_MEDIA_TYPE
    assert exported.content.read() == b"PK zip"
    [(listing, _, _, _)] = writer.lists
    assert listing.with_files
    [packed] = writer.archived
    assert [name for name, _ in packed] == [
        "Rechnungen-fr 2026-03.xlsx",
        "R20150001.pdf",
        "R20260001.pdf",
    ]
    assert packed[0][1] == b"list xlsx"
    # The imported invoice brings its original, the own one is archived on the way.
    assert packed[1][1] == b"%PDF original"
    assert packed[2][1] == f"%PDF {own} 1".encode()
    assert pdfs.calls == 1
    assert store.pdfs[own] == packed[2][1]
    assert original in store.pdfs


def test_the_zip_adds_the_attachments_after_each_pdf(
    exports: ExportHandlers,
    documents: DocumentHandlers,
    writer: RecordingWriter,
    store: Store,
) -> None:
    draft = documents.create(
        DocumentType.INVOICE,
        DraftInput(customer_id=CUSTOMER, lines=(HOURS,), issue_date=TODAY),
    )
    documents.add_file(draft.document.id, "Notar.pdf", b"%PDF-1.4 notary")
    documents.add_file(draft.document.id, "Amt.pdf", b"%PDF-1.4 office")
    documents.issue(draft.document.id)
    later = invoice(documents)
    exports.export(ExportRequest(MARCH, ExportFormat.CSV, with_pdfs=True))
    [packed] = writer.archived
    assert [name for name, _ in packed] == [
        "Rechnungen-fr 2026-03.csv",
        "R20260001.pdf",
        "R20260001_Amt.pdf",
        "R20260001_Notar.pdf",
        "R20260002.pdf",
    ]
    assert packed[2][1] == b"%PDF-1.4 office"
    assert packed[3][1] == b"%PDF-1.4 notary"
    assert later in store.pdfs
    # Without the PDFs the attachments are not even looked up.
    exports.export(ExportRequest(MARCH, ExportFormat.CSV))
    assert len(writer.archived) == 1
    # One that vanished on the way (issued documents keep theirs) is left out.
    [first, _] = documents.attachments(draft.document.id)
    del store.attachments[first.id]
    listing = writer.lists[0][0]
    files = list(exports._files("x.csv", b"", listing))  # noqa: SLF001 - the generator itself
    assert [name for name, _ in files] == [
        "x.csv",
        "R20260001.pdf",
        "R20260001_Notar.pdf",
        "R20260002.pdf",
    ]


def test_the_company_must_be_set_up(exports: ExportHandlers, store: Store) -> None:
    store.company = None
    with raises_exactly(ConflictError, "set up the company before exporting") as error:
        exports.export(ExportRequest(MARCH, ExportFormat.CSV))
    assert error.value.code == "company_not_set_up"


def test_one_export_at_a_time(exports: ExportHandlers) -> None:
    exports.running.acquire()
    try:
        with raises_exactly(ConflictError, "another export is being prepared") as error:
            exports.export(ExportRequest(MARCH, ExportFormat.CSV))
        assert error.value.code == "export_busy"
    finally:
        exports.running.release()
    assert exports.export(ExportRequest(MARCH, ExportFormat.CSV)).name.endswith(".csv")
    assert not exports.running.locked()


def test_a_failed_export_frees_the_next(exports: ExportHandlers, store: Store) -> None:
    store.company = None
    with pytest.raises(ConflictError):
        exports.export(ExportRequest(MARCH, ExportFormat.CSV))
    assert not exports.running.locked()


def test_no_pdf_is_named_like_the_list(
    exports: ExportHandlers, writer: RecordingWriter, store: Store
) -> None:
    document_id = add_imported(store, with_pdf=True)
    stored = store.documents[document_id]
    renamed = replace(stored.document, number="Rechnungen-fr 2026-03")
    store.documents[document_id] = replace(stored, document=renamed)
    exports.export(ExportRequest(MARCH, ExportFormat.PDF, with_pdfs=True))
    [packed] = writer.archived
    assert [name for name, _ in packed] == [
        "Rechnungen-fr 2026-03.pdf",
        "Rechnungen-fr 2026-03 (2).pdf",
    ]
