"""Payment codes on invoices: Swiss QR-bill (CH/LI) and EPC QR code (DE/AT, CH/LI to the EU)."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from qrbill import QRBill
from segno import helpers as segno_helpers

from rhinvoice.application.document.handlers import DocumentHandlers, DraftInput, LineInput
from rhinvoice.application.document.printing import PrintHandlers, PrintModel
from rhinvoice.domain.customer.customer import CustomerKind
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import LineKind
from rhinvoice.domain.payment.reference import creditor_reference
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.country import CountryCode
from rhinvoice.domain.shared.iban import Bic, Iban
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from rhinvoice.domain.tax.vat_number import VatNumber
from rhinvoice.infrastructure.payment import qr_bill
from rhinvoice.infrastructure.payment.epc import epc_qr
from rhinvoice.infrastructure.payment.qr_bill import payment_reference, swiss_qr_bill, swiss_text
from rhinvoice.infrastructure.rendering.html import JinjaDocumentRenderer
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories
from tests.unit.domain.factories import CH_IBAN, CH_QR_IBAN

CUSTOMER = UUID(int=1)
LINE = LineInput(kind=LineKind.ITEM, description="Beratung", quantity="2", unit_price="150")
DE_IBAN = "DE89370400440532013000"  # EPC example IBAN


@pytest.fixture
def store() -> Store:
    store = Store()
    store.company = factories.company()
    account = factories.bank_account(is_default=True)
    store.bank_accounts[account.id] = account
    store.customers[CUSTOMER] = factories.customer(id=CUSTOMER)
    return store


def printing(store: Store) -> PrintHandlers:
    def uow() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(store)

    clock = FixedClock(NOW)
    return PrintHandlers(
        uow=uow,
        clock=clock,
        documents=DocumentHandlers(uow=uow, clock=clock),
        renderer=JinjaDocumentRenderer(),
    )


def draft(**overrides: object) -> DraftInput:
    values: dict[str, object] = {"customer_id": CUSTOMER, "lines": (LINE,)}
    values.update(overrides)
    return DraftInput(**values)  # type: ignore[arg-type]  # test builder


def preview(
    store: Store, document_type: DocumentType = DocumentType.INVOICE, **overrides: object
) -> PrintModel:
    handlers = printing(store)
    return handlers.model(handlers.documents.preview(document_type, draft(**overrides)).view)


def issued(store: Store, **overrides: object) -> PrintModel:
    handlers = printing(store)
    created = handlers.documents.create(DocumentType.INVOICE, draft(**overrides)).document
    return handlers.model(handlers.documents.issue(created.id))


def cancellation_of(store: Store, invoice: PrintModel) -> PrintModel:
    handlers = printing(store)
    cancelled = handlers.documents.cancel(invoice.view.document.id).document
    assert cancelled.cancellation_id is not None
    return handlers.model(handlers.documents.get(cancelled.cancellation_id))


def qr_svg(model: PrintModel) -> str:
    svg = swiss_qr_bill(model, f"Rechnung {model.view.document.number}")
    assert svg is not None
    return svg


def test_qr_bill_with_an_iban_uses_a_creditor_reference(store: Store) -> None:
    model = issued(store)
    svg = qr_svg(model)
    assert svg.startswith("<svg")
    assert "<?xml" not in svg
    assert "CH93 0076 2011 6238 5295 7" in svg
    # 2 x 150 plus 8.1 % VAT
    assert "324.30" in svg
    assert "Rechnung R20260001" in svg
    assert "RF55 R202 6000 1" in svg
    assert "Beispiel AG" in svg
    assert "Zahlteil" in svg


@pytest.mark.parametrize(
    ("language", "receipt", "payment_part"),
    [
        (Language.FR, "Récépissé", "Section paiement"),
        (Language.IT, "Ricevuta", "Sezione pagamento"),
    ],
)
def test_qr_bill_speaks_the_document_language(
    store: Store, language: Language, receipt: str, payment_part: str
) -> None:
    svg = qr_svg(issued(store, language=language))
    assert receipt in svg
    assert payment_part in svg


def test_qr_bill_with_a_qr_iban_uses_a_qr_reference(store: Store) -> None:
    for account in list(store.bank_accounts.values()):
        store.bank_accounts[account.id] = replace(account, qr_iban=Iban(CH_QR_IBAN))
    svg = qr_svg(issued(store, language=Language.EN))
    assert "CH44 3199 9123 0008 8901 2" in svg
    assert "Payment part" in svg
    # Year 2026 and the digits of R20260001, with the check digit.
    assert "00 00000 00000 00202 62026 00017" in svg


def test_references_fall_back_when_the_number_does_not_fit() -> None:
    account = factories.bank_account(qr_iban=Iban(CH_QR_IBAN))
    plain = factories.bank_account()
    on = date(2026, 3, 9)
    assert payment_reference(account, "R20260042", on) == (
        CH_QR_IBAN,
        "000000000000002026202600426",
    )
    # 23 digits give no QR reference (and no creditor reference): the IBAN without one.
    assert payment_reference(account, "1" * 22, on)[0] == CH_QR_IBAN
    assert payment_reference(account, "1" * 23, on) == (plain.iban.value, None)
    assert payment_reference(plain, "A" * 21, on) == (
        plain.iban.value,
        creditor_reference("A" * 21),
    )
    assert payment_reference(plain, "R20260042", on) == (plain.iban.value, "RF15R20260042")
    assert payment_reference(plain, "R-" + "1" * 21, on) == (plain.iban.value, None)


def test_long_numbers_still_get_a_payment_part(store: Store) -> None:
    model = issued(store)
    number = "RECHNUNG-2026-03-0000000001"
    document = replace(model.view.document, number=number)
    svg = qr_svg(replace(model, view=replace(model.view, document=document)))
    assert "CH93 0076 2011 6238 5295 7" in svg
    assert "Referenz" not in svg


def test_text_is_limited_to_the_character_set() -> None:
    assert swiss_text("Müller & Søn, Łódź, Ștefan, 5 €") == "Müller & Søn, Łódź, Ștefan, 5 €"
    assert swiss_text("Café 😀 ǅuro\nZeile  2\t") == "Café Džuro Zeile 2"
    # Not in the set, nor composed: the base letter (Latin Extended-B "ǎ").
    assert swiss_text("ǎ") == "a"
    assert swiss_text("\u201eQuote\u201c") == "Quote"


def test_qr_bill_data_is_cleaned(store: Store) -> None:
    store.customers[CUSTOMER] = factories.customer(id=CUSTOMER, company_name="Müller 😀 AG")
    assert "Müller AG" in qr_svg(issued(store))


def test_drafts_show_where_the_payment_part_will_be(store: Store) -> None:
    model = preview(store)
    assert swiss_qr_bill(model, "Rechnung") is None
    html = JinjaDocumentRenderer().html(model)
    body = html.split("</style>", 1)[1]
    assert (
        '<div class="qr-bill pending"><p>Der QR-Zahlteil wird beim Ausstellen erstellt.</p>' in body
    )
    assert "<svg" not in body
    assert body.count('class="watermark"') == 2


def test_the_payer_is_left_out_when_the_qr_bill_refuses_it(
    store: Store, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    real = QRBill
    debtors: list[object] = []

    def strict(**values: Any) -> QRBill:  # noqa: ANN401 - the arguments of QRBill
        debtors.append(values["debtor"])
        if values["debtor"] is not None:
            raise ValueError("refused")
        return real(**values)

    monkeypatch.setattr(qr_bill, "QRBill", strict)
    model = issued(store)
    svg = qr_svg(model)
    assert "Beispiel AG" not in svg
    assert debtors[0] is not None
    assert debtors[1:] == [None]
    assert f"QR-bill of document {model.view.document.id} refused its data" in caplog.text


def test_data_the_qr_bill_refuses_leaves_it_out(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []

    def refuse(**values: Any) -> QRBill:  # noqa: ANN401 - the arguments of QRBill
        calls.append(values["debtor"])
        raise ValueError("refused")

    monkeypatch.setattr(qr_bill, "QRBill", refuse)
    model = issued(store)
    assert swiss_qr_bill(model, "Rechnung") is None
    assert len(calls) == 2
    assert swiss_qr_bill(replace(model, recipient=None), "Rechnung") is None
    assert calls[2:] == [None]


def test_qr_bill_without_a_customer(store: Store) -> None:
    svg = qr_svg(replace(issued(store), recipient=None))
    assert "Beispiel AG" not in svg


def test_long_names_of_persons_are_shortened(store: Store) -> None:
    person = factories.customer(
        id=CUSTOMER,
        kind=CustomerKind.PERSON,
        company_name="",
        first_name="A" * 50,
        last_name="B" * 50,
    )
    svg = qr_svg(replace(issued(store), recipient=person))
    assert "A" * 50 + " " + "B" * 19 + "<" in svg


@pytest.mark.parametrize(
    "change",
    [
        "quote",
        "cancellation",
        "german_company",
        "no_account",
        "german_iban",
        "other_currency",
        "zero_total",
    ],
)
def test_no_qr_bill(store: Store, change: str) -> None:
    model = issued(store)
    account = model.bank_account
    assert account is not None
    if change == "quote":
        handlers = printing(store)
        created = handlers.documents.create(DocumentType.QUOTE, draft()).document
        model = handlers.model(handlers.documents.issue(created.id))
    elif change == "cancellation":
        model = cancellation_of(store, model)
    elif change == "german_company":
        model = replace(
            model,
            company=factories.company(
                address=factories.address(country=CountryCode("DE")),
                vat_number=VatNumber.parse("DE123456789"),
            ),
        )
    elif change == "no_account":
        model = replace(model, bank_account=None)
    elif change == "german_iban":
        model = replace(model, bank_account=replace(account, iban=Iban.parse(DE_IBAN)))
    elif change == "other_currency":
        model = replace(model, bank_account=replace(account, currency=Currency.EUR))
    else:
        model = preview(store, lines=(replace(LINE, unit_price="0"),))
    assert swiss_qr_bill(model, "Rechnung") is None
    assert 'class="payment-page"' not in JinjaDocumentRenderer().html(model)


@pytest.fixture
def german(store: Store) -> Store:
    store.company = factories.company(
        name="Pixelwerk Berlin GmbH",
        address=factories.address(postal_code="10115", city="Berlin", country=CountryCode("DE")),
        default_currency=Currency.EUR,
        vat_number=VatNumber.parse("DE123456789"),
    )
    store.bank_accounts.clear()
    account = factories.bank_account(
        currency=Currency.EUR,
        iban=Iban.parse(DE_IBAN),
        bic=Bic.parse("COBADEFFXXX"),
        is_default=True,
    )
    store.bank_accounts[account.id] = account
    store.customers[CUSTOMER] = factories.customer(
        id=CUSTOMER,
        address=factories.address(postal_code="10117", city="Berlin", country=CountryCode("DE")),
    )
    return store


def test_epc_qr_for_german_invoices_in_euros(
    german: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = segno_helpers.make_epc_qr
    calls: list[dict[str, Any]] = []

    def spy(**values: Any) -> Any:  # noqa: ANN401 - segno's own types
        calls.append(values)
        return real(**values)

    monkeypatch.setattr(segno_helpers, "make_epc_qr", spy)
    model = issued(german, currency=Currency.EUR)
    svg = epc_qr(model, "Rechnung R20260001")
    assert svg is not None
    assert svg.startswith("<svg")
    assert calls == [
        {
            # The account holder, which the payer's bank compares with the account.
            "name": "Muster GmbH",
            "iban": DE_IBAN,
            # 2 x 150 plus 19 % VAT
            "amount": Decimal("357.00"),
            "text": "Rechnung R20260001",
            "bic": "COBADEFFXXX",
        }
    ]
    assert swiss_qr_bill(model, "Rechnung") is None
    html = JinjaDocumentRenderer().html(model)
    assert '<figure class="epc">' in html
    assert "Mit der Banking-App scannen und bezahlen" in html
    assert "payment-page" not in html.split("</style>", 1)[1]


def test_epc_qr_without_bic(german: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    real = segno_helpers.make_epc_qr

    def spy(**values: Any) -> Any:  # noqa: ANN401 - segno's own types
        calls.append(values)
        return real(**values)

    monkeypatch.setattr(segno_helpers, "make_epc_qr", spy)
    model = issued(german, currency=Currency.EUR)
    account = model.bank_account
    assert account is not None
    assert epc_qr(replace(model, bank_account=replace(account, bic=None)), "Rechnung") is not None
    assert calls[0]["bic"] is None


def test_german_drafts_show_where_the_qr_code_will_be(german: Store) -> None:
    model = preview(german, currency=Currency.EUR)
    assert epc_qr(model, "Rechnung") is None
    html = JinjaDocumentRenderer().html(model)
    assert '<figure class="epc pending">' in html
    assert "QR-Code zum Bezahlen folgt beim Ausstellen" in html


@pytest.mark.parametrize(
    "change",
    [
        "chf",
        "swiss_company",
        "swiss_company_without_customer",
        "no_account",
        "chf_account",
        "quote",
        "too_much",
    ],
)
def test_no_epc_qr(german: Store, change: str) -> None:
    model = issued(german, currency=Currency.EUR)
    account = model.bank_account
    assert account is not None
    if change == "chf":
        german.bank_accounts[account.id] = replace(account, currency=Currency.CHF)
        model = issued(german, currency=Currency.CHF)
    elif change == "swiss_company":
        # Swiss customers pay with the QR-bill.
        model = replace(model, company=factories.company(), recipient=factories.customer())
    elif change == "swiss_company_without_customer":
        model = replace(model, company=factories.company(), recipient=None)
    elif change == "no_account":
        model = replace(model, bank_account=None)
    elif change == "chf_account":
        model = replace(model, bank_account=replace(account, currency=Currency.CHF))
    elif change == "quote":
        model = preview(german, DocumentType.QUOTE, currency=Currency.EUR)
    else:
        model = preview(
            german,
            currency=Currency.EUR,
            lines=(replace(LINE, quantity="1000000", unit_price="1000"),),
        )
        assert model.view.totals.total.amount > Decimal("999999999.99")
    assert epc_qr(model, "Rechnung") is None
    assert "epc" not in JinjaDocumentRenderer().html(model).split("</style>", 1)[1]


LI_IBAN = "LI21088100002324013AA"  # example IBAN of Liechtenstein (EEA)


def swiss_euro_invoice(
    store: Store, *, company: str = "CH", customer: str = "AT", iban: str = CH_IBAN, bic: str | None
) -> PrintModel:
    store.company = factories.company(address=factories.address(country=CountryCode(company)))
    store.bank_accounts.clear()
    account = factories.bank_account(
        currency=Currency.EUR,
        iban=Iban.parse(iban),
        bic=None if bic is None else Bic.parse(bic),
        holder="Anna Muster",
        is_default=True,
    )
    store.bank_accounts[account.id] = account
    store.customers[CUSTOMER] = factories.customer(
        id=CUSTOMER,
        address=factories.address(
            postal_code="6900", city="Bregenz", country=CountryCode(customer)
        ),
    )
    return issued(store, currency=Currency.EUR)


@pytest.mark.parametrize(
    "case",
    [
        ("CH", "AT", CH_IBAN, "UBSWCHZH80A"),
        ("LI", "DE", LI_IBAN, None),
        ("CH", "NO", CH_IBAN, "UBSWCHZH80A"),
    ],
)
def test_swiss_euro_invoices_to_eea_customers_get_an_epc_qr_as_well(
    store: Store, monkeypatch: pytest.MonkeyPatch, case: tuple[str, str, str, str | None]
) -> None:
    company, customer, iban, bic = case
    real = segno_helpers.make_epc_qr
    calls: list[dict[str, Any]] = []

    def spy(**values: Any) -> Any:  # noqa: ANN401 - segno's own types
        calls.append(values)
        return real(**values)

    monkeypatch.setattr(segno_helpers, "make_epc_qr", spy)
    model = swiss_euro_invoice(store, company=company, customer=customer, iban=iban, bic=bic)
    assert epc_qr(model, "Rechnung R1") is not None
    assert calls == [
        {
            "name": "Anna Muster",
            "iban": iban,
            "amount": Decimal("300.00"),
            "text": "Rechnung R1",
            "bic": bic,
        }
    ]
    body = JinjaDocumentRenderer().html(model).split("</style>", 1)[1]
    assert '<figure class="epc">' in body
    assert '<div class="qr-bill"><svg' in body


@pytest.mark.parametrize(
    ("customer", "bic"),
    [
        # Swiss IBANs are outside the EEA: without a BIC the EU bank may refuse the transfer.
        ("AT", None),
        # Customers in Liechtenstein and Switzerland pay with the QR-bill.
        ("LI", "UBSWCHZH80A"),
        ("CH", "UBSWCHZH80A"),
        ("US", "UBSWCHZH80A"),
    ],
)
def test_swiss_euro_invoices_without_an_epc_qr(
    store: Store, customer: str, bic: str | None
) -> None:
    model = swiss_euro_invoice(store, customer=customer, bic=bic)
    assert epc_qr(model, "Rechnung") is None


def test_swiss_invoices_without_a_customer_get_no_epc_qr(store: Store) -> None:
    model = swiss_euro_invoice(store, bic="UBSWCHZH80A")
    assert epc_qr(replace(model, recipient=None), "Rechnung") is None


def test_the_qr_bill_names_the_account_holder(store: Store) -> None:
    store.company = factories.company(name="Pixelwerk Rheintal")
    store.bank_accounts = {
        account.id: replace(account, holder="Anna Muster")
        for account in store.bank_accounts.values()
    }
    model = issued(store)
    bill = qr_svg(model)
    assert "Anna Muster" in bill
    assert "Pixelwerk" not in bill


def test_swiss_invoices_print_the_payment_part_page(store: Store) -> None:
    html = JinjaDocumentRenderer().html(issued(store))
    body = html.split("</style>", 1)[1]
    assert '<section class="page payment-page" aria-label="Zahlteil">' in body
    assert '<div class="qr-bill"><svg' in body
    assert "epc" not in body
    assert "watermark" not in body


def test_the_date_of_supply_is_printed(store: Store) -> None:
    renderer = JinjaDocumentRenderer()
    invoice = issued(store)
    assert "<dt>Leistungsdatum</dt><dd>09.03.2026</dd>" in renderer.html(invoice)
    quote = renderer.html(preview(store, DocumentType.QUOTE))
    assert "Leistungsdatum" not in quote
    dated = renderer.html(preview(store, service_from=date(2026, 3, 1)))
    assert "<dt>Leistungsdatum</dt><dd>01.03.2026</dd>" in dated
    # A cancellation repeats the date of supply of its invoice.
    cancellation = cancellation_of(store, invoice)
    assert cancellation.view.document.type is DocumentType.CANCELLATION
    later = replace(cancellation, issue_date=date(2026, 5, 1))
    assert "<dt>Leistungsdatum</dt><dd>09.03.2026</dd>" in renderer.html(later)
