"""Imported invoices in use: their PDF, further files, printing and e-invoices."""

import hashlib
from datetime import date
from decimal import Decimal

import pytest

from rhinvoice.application.document import handlers as document_handlers
from rhinvoice.application.document.handlers import (
    DocumentHandlers,
    DraftInput,
    LineInput,
    build_index,
)
from rhinvoice.application.document.printing import PrintHandlers
from rhinvoice.application.errors import ConflictError, NotFoundError
from rhinvoice.domain.company.print_layout import PrintLayout
from rhinvoice.domain.document.document import (
    Document,
    DocumentType,
    DraftContent,
    EventKind,
    IssueSnapshot,
)
from rhinvoice.domain.document.lines import LineKind, PriceMode
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.country import Country
from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency, Money
from rhinvoice.domain.tax.treatment import TaxTreatment
from tests.helpers import raises_exactly
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store, StoredDocument
from tests.unit.application.test_printing import FakeEInvoices, RecordingRenderer
from tests.unit.domain import factories

PDF = b"%PDF-1.4 original"


@pytest.fixture
def printing(store: Store, clock: FixedClock) -> PrintHandlers:
    store.company = factories.company()
    account = factories.bank_account(is_default=True)
    store.bank_accounts[account.id] = account
    documents = DocumentHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)
    return PrintHandlers(
        uow=lambda: InMemoryUnitOfWork(store),
        clock=clock,
        documents=documents,
        renderer=RecordingRenderer(),
        e_invoices=FakeEInvoices(),
    )


def imported(store: Store, *, with_pdf: bool = True) -> Document:
    customer = factories.customer()
    store.customers[customer.id] = customer
    content = DraftContent(
        customer_id=customer.id,
        currency=Currency.CHF,
        language=Language.DE,
        price_mode=PriceMode.NET,
        lines=(),
        treatment=TaxTreatment.DOMESTIC,
        issue_date=date(2015, 2, 14),
    )
    total = Money(Decimal(108), Currency.CHF)
    document = Document.imported(
        new_id(),
        number="R20150001",
        content=content,
        snapshot=IssueSnapshot(company=factories.company(), customer=customer, bank_account=None),
        net=Money(Decimal(100), Currency.CHF),
        total=total,
        open_amount=total,
        now=NOW,
    )
    if with_pdf:
        document = document.archive_pdf(hashlib.sha256(PDF).hexdigest())
        store.pdfs[document.id] = PDF
    totals = document.totals(Country.CH, cash_rounding=False, today=date(2015, 2, 14))
    store.documents[document.id] = StoredDocument(document, build_index(document, totals, customer))
    return document


def test_the_pdf_of_an_imported_invoice_is_its_original(
    printing: PrintHandlers, store: Store
) -> None:
    document = imported(store)
    file = printing.pdf(document.id)
    assert (file.content, file.sha256) == (PDF, document.pdf_sha256)
    with raises_exactly(
        ConflictError, "an imported invoice is its PDF; it cannot be rendered"
    ) as caught:
        printing.html(document.id)
    assert caught.value.code == "imported_document"


def test_an_imported_invoice_without_pdf_is_not_rendered(
    printing: PrintHandlers, store: Store
) -> None:
    document = imported(store, with_pdf=False)
    with raises_exactly(ConflictError, "the imported invoice has no PDF yet") as caught:
        printing.pdf(document.id)
    assert caught.value.code == "imported_without_pdf"


def test_imported_invoices_are_no_e_invoices(printing: PrintHandlers, store: Store) -> None:
    document = imported(store)
    with pytest.raises(ConflictError) as caught:
        printing.e_invoice_status(document.id)
    assert caught.value.code == "not_an_e_invoice"


def test_the_layout_preview_shows_an_invoice_written_here(
    printing: PrintHandlers, store: Store
) -> None:
    imported(store)
    customer_id = next(iter(store.customers))
    line = LineInput(kind=LineKind.ITEM, description="Beratung", quantity="1", unit_price="10")
    own = printing.documents.create(
        DocumentType.INVOICE, DraftInput(customer_id=customer_id, lines=(line,))
    )
    printing.documents.issue(own.document.id)
    printing.layout_preview_html(PrintLayout())
    renderer = printing.renderer
    assert isinstance(renderer, RecordingRenderer)
    assert renderer.models[-1].view.document.id == own.document.id


def test_a_missing_pdf_is_added_once_then_files_become_attachments(
    store: Store, clock: FixedClock
) -> None:
    store.company = factories.company()
    handlers = DocumentHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)
    document = imported(store, with_pdf=False)

    locked: list[InMemoryUnitOfWork] = []

    def recording() -> InMemoryUnitOfWork:
        unit = InMemoryUnitOfWork(store)
        locked.append(unit)
        return unit

    view = DocumentHandlers(uow=recording, clock=clock).add_file(document.id, "Scan_0042.pdf", PDF)
    # Locked while the file is added: two at once must not both become the original.
    assert locked[0].documents.locked == [document.id]
    assert store.documents[document.id].document.events[-1].at == NOW
    assert view.document.pdf_sha256 == hashlib.sha256(PDF).hexdigest()
    assert store.pdfs[document.id] == PDF
    assert store.documents[document.id].document.events[-1].kind is EventKind.FILE_ADDED
    assert handlers.attachments(document.id) == []

    reminder = b"%PDF-1.4 reminder"
    handlers.add_file(document.id, "Mahnung.pdf", reminder)
    handlers.add_file(document.id, "Mahnung 2.pdf", reminder + b"2")
    second, attachment = handlers.attachments(document.id)
    assert attachment.id != second.id
    assert (attachment.file_name, attachment.size, attachment.added_at) == (
        "Mahnung.pdf",
        len(reminder),
        NOW,
    )
    assert handlers.attachment(document.id, attachment.id) == (attachment, reminder)
    stored = store.documents[document.id].document
    assert [event.detail for event in stored.events if event.kind is EventKind.FILE_ADDED] == [
        "Scan_0042.pdf",
        "Mahnung.pdf",
        "Mahnung 2.pdf",
    ]
    # The original stays as it was.
    assert store.pdfs[document.id] == PDF


def test_files_are_checked_before_they_are_added(
    store: Store, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.company = factories.company()
    handlers = DocumentHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)
    document = imported(store)
    with raises_exactly(ValidationError, "the file is no PDF") as caught:
        handlers.add_file(document.id, "x.png", b"\x89PNG")
    assert (caught.value.field, caught.value.code) == ("file", "not_a_pdf")
    monkeypatch.setattr(document_handlers, "MAX_ADDED_FILE_BYTES", len(PDF))
    with raises_exactly(ValidationError, "the file is larger than 20 MB") as caught:
        handlers.add_file(document.id, "big.pdf", PDF + b"x")
    assert (caught.value.field, caught.value.code) == ("file", "file_too_large")
    with pytest.raises(NotFoundError):
        handlers.add_file(new_id(), "x.pdf", PDF)


def test_files_are_added_to_imported_invoices_only(store: Store, clock: FixedClock) -> None:
    store.company = factories.company()
    handlers = DocumentHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)
    customer = factories.customer()
    store.customers[customer.id] = customer
    line = LineInput(kind=LineKind.ITEM, description="Beratung", quantity="1", unit_price="10")
    own = handlers.create(DocumentType.INVOICE, DraftInput(customer_id=customer.id, lines=(line,)))
    with raises_exactly(InvalidStateError, "files are added to imported invoices only"):
        handlers.add_file(own.document.id, "x.pdf", PDF)


def test_unknown_attachments_are_not_found(store: Store, clock: FixedClock) -> None:
    store.company = factories.company()
    handlers = DocumentHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)
    document = imported(store)
    with raises_exactly(NotFoundError, "attachment not found"):
        handlers.attachment(document.id, new_id())
    with pytest.raises(NotFoundError):
        handlers.attachments(new_id())
    other = imported(store)
    handlers.add_file(other.id, "Mahnung.pdf", PDF + b"2")
    [attachment] = handlers.attachments(other.id)
    # An attachment belongs to its invoice only.
    with raises_exactly(NotFoundError, "attachment not found"):
        handlers.attachment(document.id, attachment.id)
