import hashlib
from dataclasses import replace
from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from rhinvoice.application.document.einvoice import EInvoiceProblem, EInvoiceProfile
from rhinvoice.application.document.handlers import DocumentHandlers, DraftInput, LineInput
from rhinvoice.application.document.printing import (
    EInvoiceStatus,
    PrintHandlers,
    PrintModel,
    ReminderPrint,
)
from rhinvoice.application.errors import ConflictError, NotFoundError, UnavailableError
from rhinvoice.domain.company.logo import Logo
from rhinvoice.domain.company.print_layout import PrintLayout
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import LineKind
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.country import CountryCode
from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.domain.shared.money import Currency
from rhinvoice.domain.tax.vat_number import VatNumber
from tests.helpers import raises_exactly
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories

if TYPE_CHECKING:
    from collections.abc import Callable

TODAY = NOW.date()
CUSTOMER = UUID(int=1)
HOURS = LineInput(
    kind=LineKind.ITEM, description="Beratung", quantity="2", unit="HUR", unit_price="150"
)


class RecordingRenderer:
    def __init__(self) -> None:
        self.models: list[PrintModel] = []

    def html(self, model: PrintModel) -> str:
        self.models.append(model)
        return f"<html>{model.view.document.id}</html>"

    def reminder_html(self, reminder: ReminderPrint) -> str:
        return f"<html>{reminder.reminder.id}</html>"


@pytest.fixture
def renderer() -> RecordingRenderer:
    return RecordingRenderer()


@pytest.fixture
def units() -> list[InMemoryUnitOfWork]:
    """Every unit of work the handlers opened, in order."""
    return []


@pytest.fixture
def printing(
    store: Store,
    clock: FixedClock,
    renderer: RecordingRenderer,
    units: list[InMemoryUnitOfWork],
) -> PrintHandlers:
    store.company = factories.company(payment_terms_days=20)
    for account in (
        factories.bank_account(is_default=True),
        factories.bank_account(is_default=False),
        factories.bank_account(currency=Currency.EUR, is_default=True),
    ):
        store.bank_accounts[account.id] = account
    store.customers[CUSTOMER] = factories.customer(id=CUSTOMER, payment_terms_days=None)

    def uow() -> InMemoryUnitOfWork:
        unit = InMemoryUnitOfWork(store)
        units.append(unit)
        return unit

    documents = DocumentHandlers(uow=uow, clock=clock)
    return PrintHandlers(uow=uow, clock=clock, documents=documents, renderer=renderer)


def draft(**overrides: object) -> DraftInput:
    values: dict[str, object] = {"customer_id": CUSTOMER, "lines": (HOURS,)}
    values.update(overrides)
    return DraftInput(**values)  # type: ignore[arg-type]  # test builder


def test_drafts_print_with_current_data_and_derived_dates(
    printing: PrintHandlers, renderer: RecordingRenderer, store: Store
) -> None:
    created = printing.documents.create(DocumentType.INVOICE, draft())
    html = printing.html(created.document.id)
    assert html == f"<html>{created.document.id}</html>"
    [model] = renderer.models
    assert model.is_draft
    assert model.company == store.company
    assert model.recipient == store.customers[CUSTOMER]
    default_chf = next(
        a for a in store.bank_accounts.values() if a.currency is Currency.CHF and a.is_default
    )
    assert model.bank_account == default_chf
    assert model.logo is None
    # Not dated yet: printed with today and the company's payment terms.
    assert (model.issue_date, model.due_date) == (TODAY, date(2026, 3, 29))
    assert model.cancelled_number is None


def test_customer_terms_and_given_dates_win(
    printing: PrintHandlers, renderer: RecordingRenderer, store: Store
) -> None:
    store.customers[CUSTOMER] = replace(store.customers[CUSTOMER], payment_terms_days=10)
    printing.preview_html(DocumentType.INVOICE, draft())
    printing.preview_html(
        DocumentType.INVOICE,
        draft(issue_date=date(2026, 3, 1), due_date=date(2026, 3, 31), currency=Currency.EUR),
    )
    printing.preview_html(DocumentType.QUOTE, draft(issue_date=date(2026, 3, 1)))
    first, second, quote = renderer.models
    assert (first.issue_date, first.due_date) == (TODAY, date(2026, 3, 19))
    assert (second.issue_date, second.due_date) == (date(2026, 3, 1), date(2026, 3, 31))
    assert second.bank_account is not None
    assert second.bank_account.currency is Currency.EUR
    assert quote.due_date == date(2026, 3, 31)
    # The preview is not saved.
    assert store.documents == {}


def test_issued_documents_print_their_snapshot(
    printing: PrintHandlers, renderer: RecordingRenderer, store: Store
) -> None:
    created = printing.documents.create(DocumentType.INVOICE, draft())
    issued = printing.documents.issue(created.document.id).document
    snapshot = issued.issued_snapshot
    store.company = replace(snapshot.company, name="Neuer Name AG")
    store.customers[CUSTOMER] = replace(store.customers[CUSTOMER], company_name="Umbenannt AG")
    store.logo = Logo(content=b"\x89PNG", media_type="image/png")
    printing.html(issued.id)
    cancellation = printing.documents.cancel(issued.id).document.cancelled_by_id
    assert cancellation is not None
    printing.html(cancellation)
    invoice_model, cancellation_model = renderer.models
    assert not invoice_model.is_draft
    assert invoice_model.company == snapshot.company
    assert invoice_model.recipient == snapshot.customer
    assert invoice_model.bank_account == snapshot.bank_account
    assert invoice_model.logo == store.logo
    assert (invoice_model.issue_date, invoice_model.due_date) == (TODAY, date(2026, 3, 29))
    assert invoice_model.cancelled_number is None
    assert cancellation_model.cancelled_number == issued.number
    assert cancellation_model.bank_account is None


def test_converted_invoices_do_not_print_a_cancelled_number(
    printing: PrintHandlers, renderer: RecordingRenderer
) -> None:
    quote = printing.documents.create(DocumentType.QUOTE, draft()).document
    printing.documents.issue(quote.id)
    invoice = printing.documents.convert_to_invoice(quote.id).document
    issued = printing.documents.issue(invoice.id).document
    assert issued.source_id == quote.id
    printing.html(issued.id)
    assert renderer.models[-1].cancelled_number is None


class RecordingPdf:
    """Returns a PDF per call; ``during`` runs while rendering (concurrent requests)."""

    def __init__(self) -> None:
        self.calls = 0
        self.e_invoices: list[bytes | None] = []
        self.during: Callable[[], None] | None = None

    def pdf(self, model: PrintModel, e_invoice: bytes | None = None) -> bytes:
        self.calls += 1
        self.e_invoices.append(e_invoice)
        if self.during is not None:
            self.during()
        return f"%PDF {model.view.document.id} {self.calls}".encode()

    def reminder_pdf(self, reminder: ReminderPrint) -> bytes:
        return f"%PDF {reminder.reminder.id}".encode()


def with_pdf(printing: PrintHandlers, renderer: RecordingPdf | None) -> PrintHandlers:
    return replace(printing, pdf_renderer=renderer)


def test_drafts_render_a_new_pdf_each_time(printing: PrintHandlers, store: Store) -> None:
    pdf = RecordingPdf()
    handlers = with_pdf(printing, pdf)
    created = handlers.documents.create(DocumentType.INVOICE, draft()).document
    first = handlers.pdf(created.id)
    second = handlers.pdf(created.id)
    assert (first.document.id, first.sha256) == (created.id, None)
    assert first.content != second.content
    assert pdf.calls == 2
    assert store.pdfs == {}


def test_issued_documents_archive_their_first_pdf(
    printing: PrintHandlers, store: Store, units: list[InMemoryUnitOfWork]
) -> None:
    pdf = RecordingPdf()
    handlers = with_pdf(printing, pdf)
    created = handlers.documents.create(DocumentType.INVOICE, draft()).document
    issued = handlers.documents.issue(created.id).document
    first = handlers.pdf(issued.id)
    expected = hashlib.sha256(first.content).hexdigest()
    assert (first.document.number, first.sha256) == (issued.number, expected)
    assert store.pdfs == {issued.id: first.content}
    assert store.documents[issued.id].document.pdf_sha256 == expected
    # Archiving locks the document against a concurrent first download.
    assert units[-1].documents.locked == [issued.id]
    # Later requests get the archived file, also when rendering is no longer possible.
    again = with_pdf(printing, None).pdf(issued.id)
    assert again == first
    assert pdf.calls == 1


def test_a_pdf_archived_meanwhile_wins(printing: PrintHandlers, store: Store) -> None:
    created = printing.documents.create(DocumentType.INVOICE, draft()).document
    issued = printing.documents.issue(created.id).document
    other = b"%PDF from another request"

    def archive_other() -> None:
        with InMemoryUnitOfWork(store) as uow:
            document = issued.archive_pdf(hashlib.sha256(other).hexdigest())
            uow.documents.archive_pdf(document, other)
            uow.commit()

    pdf = RecordingPdf()
    pdf.during = archive_other
    assert with_pdf(printing, pdf).pdf(issued.id).content == other
    assert store.pdfs == {issued.id: other}


def test_pdfs_need_the_pdf_service(printing: PrintHandlers) -> None:
    created = printing.documents.create(DocumentType.INVOICE, draft()).document
    with raises_exactly(
        UnavailableError, "PDFs need the Gotenberg service (RHINVOICE_GOTENBERG_URL)"
    ):
        printing.pdf(created.id)
    issued = printing.documents.issue(created.id).document
    with raises_exactly(
        UnavailableError, "PDFs need the Gotenberg service (RHINVOICE_GOTENBERG_URL)"
    ):
        printing.pdf(issued.id)


def test_a_document_removed_meanwhile_is_not_found(printing: PrintHandlers, store: Store) -> None:
    created = printing.documents.create(DocumentType.INVOICE, draft()).document
    issued = printing.documents.issue(created.id).document
    pdf = RecordingPdf()

    def remove() -> None:
        del store.documents[issued.id]

    pdf.during = remove
    with raises_exactly(NotFoundError, "document not found"):
        with_pdf(printing, pdf).pdf(issued.id)


class FakeEInvoices:
    """Writes "<profile document-id>"."""

    def xml(self, model: PrintModel, profile: EInvoiceProfile) -> bytes:
        assert model.view.document.number is not None
        return f"<{profile.value} {model.view.document.id}>".encode()


XRECHNUNG_GAPS = (
    EInvoiceProblem.BUYER_REFERENCE_MISSING,
    EInvoiceProblem.SELLER_EMAIL_MISSING,
    EInvoiceProblem.SELLER_PHONE_MISSING,
    EInvoiceProblem.BUYER_EMAIL_MISSING,
)


def e_invoicing(printing: PrintHandlers) -> tuple[PrintHandlers, RecordingPdf]:
    pdf = RecordingPdf()
    return replace(printing, pdf_renderer=pdf, e_invoices=FakeEInvoices()), pdf


def issue(
    printing: PrintHandlers,
    document_type: DocumentType = DocumentType.INVOICE,
    **overrides: object,
) -> UUID:
    created = printing.documents.create(document_type, draft(**overrides)).document
    return printing.documents.issue(created.id).document.id


def test_issued_invoices_embed_their_e_invoice(printing: PrintHandlers, store: Store) -> None:
    handlers, pdf = e_invoicing(printing)
    invoice = issue(handlers)
    handlers.pdf(invoice)
    expected = f"<en16931 {invoice}>".encode()
    assert pdf.e_invoices == [expected]
    # Archived with the PDF: the status knows it from then on.
    assert store.e_invoices == {invoice: expected}
    cancellation = handlers.documents.cancel(invoice).document.cancellation_id
    handlers.pdf(cancellation)
    assert pdf.e_invoices[-1] == f"<en16931 {cancellation}>".encode()
    # Drafts and quotes are no invoices.
    draft_id = handlers.documents.create(DocumentType.INVOICE, draft()).document.id
    handlers.pdf(draft_id)
    handlers.pdf(issue(handlers, DocumentType.QUOTE))
    assert pdf.e_invoices[-2:] == [None, None]


def test_no_e_invoice_when_off_incomplete_or_not_configured(
    printing: PrintHandlers, store: Store
) -> None:
    handlers, pdf = e_invoicing(printing)
    store.print_layout = PrintLayout(e_invoice=False)
    handlers.pdf(issue(handlers))
    store.print_layout = PrintLayout()
    # Reverse charge to a customer whose VAT number has no country prefix (BR-AE-02).
    store.customers[CUSTOMER] = replace(
        store.customers[CUSTOMER],
        address=replace(store.customers[CUSTOMER].address, country=CountryCode("DE")),
        vat_number=VatNumber("123456789"),
    )
    incomplete = issue(handlers)
    assert handlers.e_invoice_status(incomplete).problems[EInvoiceProfile.EN16931] == (
        EInvoiceProblem.BUYER_VAT_ID_MISSING,
    )
    handlers.pdf(incomplete)
    replace(handlers, e_invoices=None).pdf(issue(handlers))
    assert pdf.e_invoices == [None, None, None]
    assert store.e_invoices == {}


def test_the_e_invoice_status(printing: PrintHandlers, store: Store) -> None:
    handlers, _ = e_invoicing(printing)
    # Drafts tell what they would be when issued now.
    draft_id = handlers.documents.create(DocumentType.INVOICE, draft()).document.id
    assert handlers.e_invoice_status(draft_id) == EInvoiceStatus(
        enabled=True,
        embedded=None,
        problems={EInvoiceProfile.EN16931: (), EInvoiceProfile.XRECHNUNG: XRECHNUNG_GAPS},
    )
    invoice = handlers.documents.issue(draft_id).document.id
    assert handlers.e_invoice_status(invoice).embedded is None
    handlers.pdf(invoice)
    assert handlers.e_invoice_status(invoice).embedded is True
    store.print_layout = PrintLayout(e_invoice=False)
    later = issue(handlers)
    handlers.pdf(later)
    status = handlers.e_invoice_status(later)
    assert (status.enabled, status.embedded) == (False, False)


def test_only_invoices_are_e_invoices(printing: PrintHandlers) -> None:
    handlers, _ = e_invoicing(printing)
    quote = issue(handlers, DocumentType.QUOTE)
    with raises_exactly(ConflictError, "quotes are no e-invoices") as caught:
        handlers.e_invoice_status(quote)
    assert caught.value.code == "not_an_e_invoice"
    draft_id = handlers.documents.create(DocumentType.INVOICE, draft()).document.id
    for document_id in (draft_id, quote):
        with raises_exactly(
            ConflictError, "only issued invoices and cancellations are e-invoices"
        ) as refused:
            handlers.xrechnung(document_id)
        assert refused.value.code == "not_an_e_invoice"
    for unconfigured in (printing.e_invoice_status, printing.xrechnung):
        with raises_exactly(UnavailableError, "e-invoices are not configured"):
            unconfigured(quote)


def test_xrechnung(printing: PrintHandlers, store: Store) -> None:
    handlers, _ = e_invoicing(printing)
    lacking = issue(handlers)
    with raises_exactly(
        ConflictError,
        "the invoice is no complete XRechnung: buyer_reference_missing, seller_email_missing,"
        " seller_phone_missing, buyer_email_missing",
    ) as caught:
        handlers.xrechnung(lacking)
    assert caught.value.code == "e_invoice_incomplete"
    assert store.company is not None
    store.company = replace(
        store.company, email=EmailAddress("info@muster.example"), phone="+41 71 000 00 00"
    )
    store.customers[CUSTOMER] = replace(
        store.customers[CUSTOMER], email=EmailAddress("einkauf@beispiel.example")
    )
    invoice = issue(handlers, reference="04011000-12345-34")
    document, content = handlers.xrechnung(invoice)
    assert (document.id, content) == (invoice, f"<xrechnung {invoice}>".encode())


def test_drafts_tell_what_their_e_invoice_lacks(printing: PrintHandlers, store: Store) -> None:
    handlers, _ = e_invoicing(printing)
    view = handlers.documents.preview(DocumentType.INVOICE, draft()).view
    assert handlers.draft_e_invoice_problems(view) == ()
    store.customers[CUSTOMER] = replace(
        store.customers[CUSTOMER],
        address=replace(store.customers[CUSTOMER].address, country=CountryCode("DE")),
        vat_number=VatNumber("123456789"),
    )
    lacking = handlers.documents.preview(DocumentType.INVOICE, draft()).view
    assert handlers.draft_e_invoice_problems(lacking) == (EInvoiceProblem.BUYER_VAT_ID_MISSING,)
    # Not for quotes, without customer, when switched off or not configured.
    quote = handlers.documents.preview(DocumentType.QUOTE, draft()).view
    assert handlers.draft_e_invoice_problems(quote) == ()
    assert handlers.draft_e_invoice_problems(replace(lacking, customer=None)) == ()
    assert printing.draft_e_invoice_problems(lacking) == ()
    store.print_layout = PrintLayout(e_invoice=False)
    assert handlers.draft_e_invoice_problems(lacking) == ()
