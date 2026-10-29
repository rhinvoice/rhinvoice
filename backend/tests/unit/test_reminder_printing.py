"""Payment reminders on paper: the invoice's page with the reminder's figures."""

import io
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from pypdf import PdfReader

from rhinvoice.application.document.handlers import (
    DocumentHandlers,
    DraftInput,
    LineInput,
    PaymentInput,
)
from rhinvoice.application.document.printing import PrintHandlers
from rhinvoice.application.dunning.handlers import DunningHandlers
from rhinvoice.application.errors import NotFoundError, UnavailableError
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import LineKind
from rhinvoice.domain.dunning.reminder import DEFAULT_LEVELS
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from rhinvoice.infrastructure.rendering.html import JinjaDocumentRenderer
from rhinvoice.infrastructure.rendering.pdf import (
    ChromiumPdfRenderer,
    GotenbergPrinter,
    file_name,
    reminder_title,
)
from tests.helpers import blank_pdf, raises_exactly
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories
from tests.unit.test_pdf import form_fields

CUSTOMER = UUID(int=1)
LINE = LineInput(kind=LineKind.ITEM, description="Beratung", quantity="1", unit_price="100")
TODAY = NOW.date()


@pytest.fixture
def store() -> Store:
    return Store()


def setup(
    store: Store, language: Language = Language.DE, paid: str | None = None, **account_fields: object
) -> tuple[PrintHandlers, UUID]:
    store.company = factories.company()
    account = factories.bank_account(is_default=True, **account_fields)
    store.bank_accounts[account.id] = account
    store.customers[CUSTOMER] = factories.customer(id=CUSTOMER)
    clock = FixedClock(NOW)

    def uow() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(store)

    documents = DocumentHandlers(uow=uow, clock=clock)
    due = TODAY - timedelta(days=20)
    draft = DraftInput(
        customer_id=CUSTOMER,
        lines=(LINE,),
        issue_date=due - timedelta(days=30),
        due_date=due,
        language=language,
    )
    invoice = documents.create(DocumentType.INVOICE, draft).document.id
    documents.issue(invoice)
    if paid is not None:
        documents.add_payment(invoice, PaymentInput(paid_on=TODAY, amount=paid))
    dunning = DunningHandlers(uow=uow, clock=clock, documents=documents)
    store.dunning_levels = [
        replace(level, fee=Decimal(fee))
        for level, fee in zip(DEFAULT_LEVELS, ("0", "20", "30"), strict=True)
    ]
    dunning.remind(invoice, level=1)
    second, _ = dunning.remind(invoice, level=2, early=True)
    html = JinjaDocumentRenderer()
    pdf = ChromiumPdfRenderer(
        html,
        GotenbergPrinter(
            "http://gotenberg:3000",
            httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        content=blank_pdf() + request.content[:0],
                        headers={"content-type": "application/pdf"},
                    )
                )
            ),
        ),
    )
    printing = PrintHandlers(
        uow=uow, clock=clock, documents=documents, renderer=html, pdf_renderer=pdf
    )
    return printing, second.id


def test_a_dunning_letter(store: Store) -> None:
    printing, reminder_id = setup(store)
    html = printing.reminder_html(reminder_id)
    number = next(iter(store.documents.values())).document.number
    assert "<title>1. Mahnung</title>" in html
    assert "<dt>Datum</dt>" in html
    assert "<h1>1. Mahnung</h1>" in html
    # The level's text with the new deadline.
    due = (TODAY + timedelta(days=10)).strftime("%d.%m.%Y")
    assert f"den offenen Betrag bis {due} zu überweisen" in html
    assert f"<dt>Rechnungs-Nr.</dt><dd>{number}</dd>" in html
    assert f"<dt>Zahlbar bis</dt><dd>{due}</dd>" in html
    assert 'class="pending"' not in html
    assert '<span class="">Mahngebühr</span>' in html
    assert '<span class="value ">20.00</span>' in html
    # 100 + 8.1 % VAT, rounded to 0.05, plus the fee: the QR-bill asks for all of it.
    assert '<span class="value grand">128.10</span>' in html
    assert '<div class="qr-bill"><svg' in html
    assert "128.10" in html[html.index('<div class="qr-bill">') :]


def test_a_reminder_names_the_third_party_that_collects(store: Store) -> None:
    printing, reminder_id = setup(
        store, holder="Inkasso AG", third_party=True, holder_address=factories.address()
    )
    html = printing.reminder_html(reminder_id)
    assert (
        '<p class="text payee">Zahlung an: Inkasso AG · IBAN CH93 0076 2011 6238 5295 7</p>' in html
    )


def test_a_payment_reminder_in_english_without_fee(store: Store) -> None:
    printing, _ = setup(store, Language.EN)
    first = min(store.reminders.values(), key=lambda reminder: reminder.level)
    html = printing.reminder_html(first.id)
    assert "<h1>Payment reminder</h1>" in html
    assert "Dunning fee" not in html
    assert "Perhaps it escaped your attention" in html


@pytest.mark.parametrize(
    ("language", "title", "text"),
    [
        (Language.FR, "<h1>Rappel de paiement</h1>", "Sans doute cela vous a-t-il échappé"),
        (Language.IT, "<h1>Promemoria di pagamento</h1>", "Forse vi è sfuggito"),
    ],
)
def test_payment_reminders_in_french_and_italian(
    store: Store, language: Language, title: str, text: str
) -> None:
    printing, _ = setup(store, language)
    first = min(store.reminders.values(), key=lambda reminder: reminder.level)
    html = printing.reminder_html(first.id)
    assert title in html
    assert text in html


def test_the_reminder_pdf(store: Store) -> None:
    printing, reminder_id = setup(store)
    printed, content = printing.reminder_pdf(reminder_id)
    assert content.startswith(b"%PDF-")
    number = printed.model.view.document.number
    assert reminder_title(printed) == f"1. Mahnung {number}"
    assert file_name("1. Mahnung R2026/1") == "1. Mahnung R2026-1.pdf"


def test_metadata_of_the_reminder_pdf(store: Store) -> None:
    printing, reminder_id = setup(store)
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=blank_pdf(), headers={"content-type": "application/pdf"})

    html = JinjaDocumentRenderer()
    renderer = ChromiumPdfRenderer(
        html,
        GotenbergPrinter(
            "http://gotenberg:3000", httpx.Client(transport=httpx.MockTransport(handle))
        ),
    )
    printed = printing.reminder(reminder_id)
    content = renderer.reminder_pdf(printed)
    fields = form_fields(requests[0])
    assert fields["files"].decode() == html.reminder_html(printed)
    metadata = PdfReader(io.BytesIO(content)).metadata
    assert metadata is not None
    assert metadata.title == reminder_title(printed)
    assert metadata.subject == f"Rechnung {printed.model.view.document.number}"
    # Written when the reminder was, so the PDF is the same each time.
    assert str(metadata["/CreationDate"]) == "D:20260309090000Z"
    assert PdfReader(io.BytesIO(content)).attachments == {}


def test_unknown_reminders_and_no_pdf_service(store: Store) -> None:
    printing, reminder_id = setup(store)
    with raises_exactly(NotFoundError, "reminder not found"):
        printing.reminder_html(new_id())
    without = PrintHandlers(
        uow=printing.uow,
        clock=printing.clock,
        documents=printing.documents,
        renderer=printing.renderer,
    )
    with pytest.raises(UnavailableError):
        without.reminder_pdf(reminder_id)


def test_a_reminder_without_recipient_has_no_customer_number(store: Store) -> None:
    printing, reminder_id = setup(store)
    printed = printing.reminder(reminder_id)
    html = JinjaDocumentRenderer().reminder_html(
        replace(printed, model=replace(printed.model, recipient=None))
    )
    assert "Kunden-Nr." not in html
    assert "Kunden-Nr." in printing.reminder_html(reminder_id)


def test_a_partly_paid_invoice_asks_for_the_rest_and_the_fee(store: Store) -> None:
    printing, reminder_id = setup(store, paid="50")
    html = printing.reminder_html(reminder_id)
    # 108.10 issued, 50.00 paid, 58.10 open; plus 20.00 fee.
    assert '<td class="num">108.10</td>' in html
    assert '<td class="num">50.00</td>' in html
    assert '<span class="value grand">78.10</span>' in html
    assert "78.10" in html[html.index('<div class="qr-bill">') :]
