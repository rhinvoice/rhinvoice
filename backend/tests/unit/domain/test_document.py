from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from rhinvoice.domain.catalog.unit import Unit
from rhinvoice.domain.document.document import (
    DisplayStatus,
    Document,
    DocumentEvent,
    DocumentStatus,
    DocumentType,
    DraftContent,
    EventKind,
    IssueSnapshot,
    Payment,
    default_due_date,
)
from rhinvoice.domain.document.lines import Discount, DocumentLine, LineKind, PriceMode
from rhinvoice.domain.shared.country import Country, CountryCode
from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency, Money
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply
from rhinvoice.domain.tax.treatment import TaxTreatment
from rhinvoice.domain.tax.vat_number import VatNumber
from tests.helpers import raises_exactly
from tests.unit.domain import factories

NOW = datetime(2026, 3, 9, 9, 0, tzinfo=UTC)
LATER = datetime(2026, 3, 10, 14, 30, tzinfo=UTC)
TODAY = date(2026, 3, 9)


def line(
    quantity: str = "10",
    price: str = "150",
    category: TaxCategory = TaxCategory.STANDARD,
    supply: Supply = Supply.SERVICE,
) -> DocumentLine:
    return DocumentLine(
        id=new_id(),
        kind=LineKind.ITEM,
        description="Beratung",
        quantity=Decimal(quantity),
        unit=Unit("HUR"),
        unit_price=Decimal(price),
        tax_category=category,
        supply=supply,
    )


def content(**overrides: object) -> DraftContent:
    values: dict[str, object] = {
        "customer_id": new_id(),
        "currency": Currency.CHF,
        "language": Language.DE,
        "price_mode": PriceMode.NET,
        "lines": (line(), line("3", "12.35", TaxCategory.REDUCED)),
        "treatment": TaxTreatment.DOMESTIC,
    }
    values.update(overrides)
    return DraftContent(**values)  # type: ignore[arg-type]  # test builder


def snapshot() -> IssueSnapshot:
    return IssueSnapshot(
        company=factories.company(),
        customer=factories.customer(),
        bank_account=factories.bank_account(),
    )


def draft(document_type: DocumentType = DocumentType.INVOICE, **overrides: object) -> Document:
    return Document.new_draft(new_id(), document_type, content(**overrides), NOW)


def issued(document_type: DocumentType = DocumentType.INVOICE, **overrides: object) -> Document:
    return draft(document_type, **overrides).issue(
        number="R20260001",
        issue_date=TODAY,
        due_date=TODAY + timedelta(days=30),
        snapshot=snapshot(),
        now=NOW,
    )


def pay(document: Document, amount: str, paid_on: date = TODAY) -> Document:
    payment = Payment(
        id=new_id(),
        paid_on=paid_on,
        amount=Money(Decimal(amount), Currency.CHF),
        recorded_at=NOW,
    )
    return document.add_payment(payment, NOW)


# --- Draft content -------------------------------------------------------------------


def test_draft_content_validation() -> None:
    cleaned = content(
        subject=" Webseite ", reference=" PO 1 ", intro_text=" Hallo \r\n", closing_text=" Gruss "
    )
    assert (cleaned.subject, cleaned.reference, cleaned.intro_text, cleaned.closing_text) == (
        "Webseite",
        "PO 1",
        "Hallo",
        "Gruss",
    )
    cases: list[tuple[dict[str, object], str, str]] = [
        ({"lines": tuple(line() for _ in range(501))}, "lines", "a document has at most 500 lines"),
        (
            {"service_from": date(2026, 2, 2), "service_to": date(2026, 2, 1)},
            "service_to",
            "the service period ends before it starts",
        ),
        (
            {"issue_date": date(2026, 2, 2), "due_date": date(2026, 2, 1)},
            "due_date",
            "the due date is before the document date",
        ),
        ({"subject": "x" * 201}, "subject", "subject must be at most 200 characters long"),
        ({"reference": "x" * 101}, "reference", "reference must be at most 100 characters long"),
        (
            {"intro_text": "x" * 4001},
            "intro_text",
            "intro_text must be at most 4000 characters long",
        ),
        (
            {"closing_text": "x" * 4001},
            "closing_text",
            "closing_text must be at most 4000 characters long",
        ),
    ]
    for overrides, field, message in cases:
        with pytest.raises(ValidationError) as error:
            content(**overrides)
        assert error.value.details == {field: message}
    assert len(content(lines=tuple(line() for _ in range(500))).lines) == 500
    assert content(service_from=date(2026, 2, 1), service_to=date(2026, 2, 1)).service_to == date(
        2026, 2, 1
    )
    assert content(issue_date=date(2026, 2, 1), due_date=date(2026, 2, 1)).due_date == date(
        2026, 2, 1
    )


def test_tax_date_is_the_date_of_supply() -> None:
    assert content().tax_date is None
    assert content(issue_date=date(2026, 1, 5)).tax_date == date(2026, 1, 5)
    assert content(issue_date=date(2026, 1, 5), service_from=date(2025, 12, 1)).tax_date == date(
        2025, 12, 1
    )
    assert content(service_from=date(2025, 12, 1), service_to=date(2025, 12, 31)).tax_date == date(
        2025, 12, 31
    )


def test_cancellations_cannot_be_created_directly() -> None:
    with raises_exactly(
        ValidationError, "cancellations are created by cancelling an invoice"
    ) as error:
        draft(DocumentType.CANCELLATION)
    assert error.value.field == "type"


def test_new_draft() -> None:
    document = draft()
    assert document.is_draft
    assert document.status is DocumentStatus.DRAFT
    assert document.number is None
    assert document.events[0].kind is EventKind.CREATED
    assert document.events[0].at == NOW
    assert document.paid_amount == Money.zero(Currency.CHF)
    assert document.open_amount() == Money.zero(Currency.CHF)
    with raises_exactly(InvalidStateError, "the document has no number yet"):
        _ = document.issued_number
    assert DocumentType.INVOICE.sequence.value == "invoice"


def test_new_draft_logs_a_tax_override() -> None:
    overridden = content(treatment=TaxTreatment.EXPORT, treatment_overridden=True)
    document = Document.new_draft(new_id(), DocumentType.INVOICE, overridden, NOW)
    assert [(event.at, event.kind, event.detail) for event in document.events] == [
        (NOW, EventKind.CREATED, ""),
        (NOW, EventKind.TAX_OVERRIDDEN, "export"),
    ]
    reasoned = Document.new_draft(
        new_id(), DocumentType.INVOICE, overridden, NOW, override_reason=" Nachweis "
    )
    assert reasoned.events[-1].detail == "export: Nachweis"


def test_draft_totals_use_the_current_rates_of_the_date_of_supply() -> None:
    old = draft(service_to=date(2023, 12, 31)).totals(Country.CH, cash_rounding=True, today=TODAY)
    new = draft(service_to=date(2024, 1, 1)).totals(Country.CH, cash_rounding=True, today=TODAY)
    assert [group.rate for group in old.groups] == [Decimal("7.7"), Decimal("2.5")]
    assert [group.rate for group in new.groups] == [Decimal("8.1"), Decimal("2.6")]
    german = draft().totals(Country.DE, cash_rounding=False, today=TODAY)
    assert [group.rate for group in german.groups] == [Decimal(19), Decimal(7)]
    # Without dates a draft uses the rates of today, not of the day it was created.
    created_in_2023 = replace(draft(), created_at=datetime(2023, 6, 1, tzinfo=UTC))
    swiss = created_in_2023.totals(Country.CH, cash_rounding=True, today=date(2024, 1, 2))
    assert [group.rate for group in swiss.groups] == [Decimal("8.1"), Decimal("2.6")]


# --- Editing and override log ---------------------------------------------------------------


def test_edit_logs_tax_overrides_once() -> None:
    document = draft()
    edited = document.edit(content(subject="Neu"), NOW)
    assert edited.content.subject == "Neu"
    assert edited.events == document.events
    overridden = edited.edit(
        content(treatment=TaxTreatment.EXPORT, treatment_overridden=True),
        LATER,
        override_reason="Ausfuhr mit Nachweis",
    )
    assert overridden.events[-1].kind is EventKind.TAX_OVERRIDDEN
    assert overridden.events[-1].at == LATER
    assert overridden.events[-1].detail == "export: Ausfuhr mit Nachweis"
    again = overridden.edit(content(treatment=TaxTreatment.EXPORT, treatment_overridden=True), NOW)
    assert again.events == overridden.events
    changed = again.edit(content(treatment=TaxTreatment.EXEMPT, treatment_overridden=True), NOW)
    assert changed.events[-1].detail == "exempt"


def test_issued_documents_cannot_be_edited_or_deleted() -> None:
    document = issued()
    with raises_exactly(InvalidStateError, "a issued invoice cannot be changed"):
        document.edit(content(), NOW)
    with raises_exactly(InvalidStateError, "a issued invoice cannot be deleted"):
        document.delete_check()
    draft().delete_check()


def test_cancellation_id() -> None:
    with raises_exactly(InvalidStateError, "the document has not been cancelled"):
        _ = issued().cancellation_id
    cancellation = new_id()
    assert replace(issued(), cancelled_by_id=cancellation).cancellation_id == cancellation


def test_the_pdf_of_issued_documents_is_archived_once() -> None:
    sha = "a" * 64
    with raises_exactly(InvalidStateError, "drafts have no archived PDF"):
        draft().archive_pdf(sha)
    document = issued()
    assert document.pdf_sha256 is None
    archived = document.archive_pdf(sha)
    assert archived.pdf_sha256 == sha
    assert archived.events == document.events
    with raises_exactly(InvalidStateError, "the PDF of this document is already archived"):
        archived.archive_pdf(sha)
    for wrong in ("A" * 64, "a" * 63, "a" * 65, "g" * 64, f" {'a' * 64}"):
        with raises_exactly(ValidationError, "a SHA-256 hash has 64 lowercase hex digits") as error:
            document.archive_pdf(wrong)
        assert error.value.field == "pdf_sha256"


# --- Issuing ---------------------------------------------------------------------------------


def test_issue_freezes_rates_totals_and_parties() -> None:
    document = issued(service_to=date(2023, 12, 1))
    assert document.status is DocumentStatus.ISSUED
    assert document.number == "R20260001"
    assert document.issued_number == "R20260001"
    assert document.issued_at == NOW
    assert document.content.issue_date == TODAY
    assert document.content.due_date == TODAY + timedelta(days=30)
    assert [line.tax_rate for line in document.content.lines] == [Decimal("7.7"), Decimal("2.5")]
    assert document.snapshot is not None
    assert document.issued_totals is not None
    # 2023 rates: 1500 x 7.7 % = 115.50, 37.05 x 2.5 % = 0.93 -> 1653.48 -> 1653.50
    assert document.issued_totals.total == Money(Decimal("1653.50"), Currency.CHF)
    assert document.totals(Country.DE, cash_rounding=False, today=TODAY) is document.issued_totals
    assert document.events[-1].kind is EventKind.ISSUED
    assert document.events[-1].detail == "R20260001"
    assert document.open_amount() == document.issued_totals.total


def test_text_lines_get_no_rate_and_euro_amounts_are_not_cash_rounded() -> None:
    text = DocumentLine(id=new_id(), kind=LineKind.TEXT, description="Phase 1")
    document = issued(lines=(text, line("1", "10.01")), currency=Currency.EUR)
    assert [item.tax_rate for item in document.content.lines] == [None, Decimal("8.1")]
    assert document.issued_totals is not None
    assert document.issued_totals.total.amount == Decimal("10.82")


def test_issue_requires_a_position_and_a_valid_due_date() -> None:
    text = DocumentLine(id=new_id(), kind=LineKind.TEXT, description="Nur Text")
    with raises_exactly(
        ValidationError, "the document needs at least one position with an amount"
    ) as lines:
        draft(lines=(text,)).issue(
            number="R1", issue_date=TODAY, due_date=TODAY, snapshot=snapshot(), now=NOW
        )
    assert lines.value.field == "lines"
    with raises_exactly(ValidationError, "the due date is before the document date") as due:
        draft().issue(
            number="R1",
            issue_date=TODAY,
            due_date=TODAY - timedelta(days=1),
            snapshot=snapshot(),
            now=NOW,
        )
    assert due.value.field == "due_date"
    with raises_exactly(InvalidStateError, "a issued invoice cannot be issued"):
        issued().issue(number="R2", issue_date=TODAY, due_date=TODAY, snapshot=snapshot(), now=NOW)


def test_issued_documents_use_the_company_country_and_rounding_of_the_snapshot() -> None:
    company = factories.company(
        address=factories.address(country=CountryCode("DE")), cash_rounding=False
    )
    document = draft().issue(
        number="R1",
        issue_date=TODAY,
        due_date=TODAY,
        snapshot=IssueSnapshot(company=company, customer=factories.customer(), bank_account=None),
        now=NOW,
    )
    assert [line.tax_rate for line in document.content.lines] == [Decimal(19), Decimal(7)]
    assert document.issued_totals is not None
    assert document.issued_totals.total.amount == Decimal("1824.64")


def test_goods_lines_use_the_goods_treatment() -> None:
    goods = line("2", "50", supply=Supply.GOODS)
    document = draft(
        lines=(line(), goods),
        treatment=TaxTreatment.DOMESTIC,
        goods_treatment=TaxTreatment.GOODS_EXPORT,
    )
    assert document.content.treatment_of(goods) is TaxTreatment.GOODS_EXPORT
    assert document.content.treatment_of(line()) is TaxTreatment.DOMESTIC
    assert document.content.treatments == (TaxTreatment.DOMESTIC, TaxTreatment.GOODS_EXPORT)
    assert document.content.charges_vat
    totals = document.totals(Country.CH, cash_rounding=False, today=TODAY)
    assert [group.tax.amount for group in totals.groups] == [Decimal("121.50"), Decimal(0)]
    # Without goods lines only the document's treatment counts.
    services = draft(goods_treatment=TaxTreatment.GOODS_EXPORT).content
    assert services.treatments == (TaxTreatment.DOMESTIC,)
    only_goods = draft(lines=(goods,), goods_treatment=TaxTreatment.GOODS_EXPORT).content
    assert only_goods.treatments == (TaxTreatment.GOODS_EXPORT,)
    assert not only_goods.charges_vat
    # A goods treatment equal to the document's is just the document's.
    same = draft(lines=(goods,), goods_treatment=TaxTreatment.DOMESTIC).content
    assert same.treatments == (TaxTreatment.DOMESTIC,)
    text = DocumentLine(id=new_id(), kind=LineKind.TEXT, description="Nur Text")
    assert draft(lines=(text,)).content.charges_vat
    # The document's treatment comes first, whatever the order of the lines; text
    # lines have none.
    goods_first = draft(
        lines=(text, goods, line()), goods_treatment=TaxTreatment.GOODS_EXPORT
    ).content
    assert goods_first.treatments == (TaxTreatment.DOMESTIC, TaxTreatment.GOODS_EXPORT)
    with_text = draft(lines=(text, goods), goods_treatment=TaxTreatment.GOODS_EXPORT).content
    assert with_text.treatments == (TaxTreatment.GOODS_EXPORT,)


def test_goods_treatments_are_not_a_document_treatment() -> None:
    with raises_exactly(
        ValidationError, "goods get this treatment from reverse charge or an export"
    ) as error:
        content(treatment=TaxTreatment.INTRA_COMMUNITY)
    assert (error.value.field, error.value.code) == ("treatment_override", "goods_only_treatment")
    with raises_exactly(ValidationError, "this treatment does not apply to goods") as goods:
        content(goods_treatment=TaxTreatment.EXPORT)
    assert goods.value.field == "treatment_override"


def test_an_intra_community_supply_names_the_vat_id_of_the_company() -> None:
    german = factories.company(
        address=factories.address(country=CountryCode("DE")), vat_number=None, tax_number="12/345"
    )
    customer = factories.customer(vat_number=VatNumber.parse("ATU12345675"))
    supply = draft(
        lines=(line(supply=Supply.GOODS),),
        currency=Currency.EUR,
        treatment=TaxTreatment.REVERSE_CHARGE,
        goods_treatment=TaxTreatment.INTRA_COMMUNITY,
    )
    with raises_exactly(
        ValidationError, "an intra-Community supply states the VAT ID of the company"
    ) as error:
        supply.issue(
            number="R1",
            issue_date=TODAY,
            due_date=TODAY,
            snapshot=IssueSnapshot(company=german, customer=customer, bank_account=None),
            now=NOW,
        )
    assert (error.value.field, error.value.code) == ("company", "company_vat_id_missing")
    registered = replace(german, vat_number=VatNumber.parse("DE123456789"))
    with raises_exactly(
        ValidationError, "an intra-Community supply states the VAT ID of the customer"
    ) as customer_error:
        # Reverse charge checks the customer's number first; goods alone check it too.
        replace(supply, content=replace(supply.content, treatment=TaxTreatment.DOMESTIC)).issue(
            number="R1",
            issue_date=TODAY,
            due_date=TODAY,
            snapshot=IssueSnapshot(
                company=registered,
                customer=replace(customer, vat_number=None),
                bank_account=None,
            ),
            now=NOW,
        )
    assert (customer_error.value.field, customer_error.value.code) == (
        "customer_id",
        "customer_vat_id_missing",
    )
    # A quote is no invoice: nothing to check.
    quote = replace(supply, type=DocumentType.QUOTE).issue(
        number="A1",
        issue_date=TODAY,
        due_date=TODAY,
        snapshot=IssueSnapshot(company=german, customer=customer, bank_account=None),
        now=NOW,
    )
    assert quote.status is DocumentStatus.SENT
    # Services alone are reverse charge, where the tax number is enough here.
    services = replace(supply, content=replace(supply.content, lines=(line(),)))
    issued_services = services.issue(
        number="R1",
        issue_date=TODAY,
        due_date=TODAY,
        snapshot=IssueSnapshot(company=german, customer=customer, bank_account=None),
        now=NOW,
    )
    assert issued_services.status is DocumentStatus.ISSUED


# --- Quotes ------------------------------------------------------------------------------------


def test_quote_flow() -> None:
    quote = issued(DocumentType.QUOTE)
    assert quote.status is DocumentStatus.SENT
    assert quote.events[-1].kind is EventKind.SENT
    accepted = quote.accept(LATER)
    assert accepted.status is DocumentStatus.ACCEPTED
    assert accepted.events[-1] == DocumentEvent(LATER, EventKind.ACCEPTED, "")
    declined = quote.decline(LATER)
    assert declined.status is DocumentStatus.DECLINED
    assert declined.events[-1] == DocumentEvent(LATER, EventKind.DECLINED, "")
    with raises_exactly(InvalidStateError, "a accepted quote cannot be accepted"):
        accepted.accept(NOW)
    with raises_exactly(InvalidStateError, "a draft quote cannot be declined"):
        draft(DocumentType.QUOTE).decline(NOW)


def test_converting_a_quote() -> None:
    quote = issued(DocumentType.QUOTE)
    invoice_id = new_id()
    converted = quote.mark_converted(invoice_id, LATER)
    assert converted.status is DocumentStatus.ACCEPTED
    assert converted.converted_to_id == invoice_id
    assert converted.events[-1] == DocumentEvent(LATER, EventKind.CONVERTED, str(invoice_id))
    accepted = quote.accept(NOW).mark_converted(invoice_id, NOW)
    assert accepted.status is DocumentStatus.ACCEPTED
    with raises_exactly(
        InvalidStateError, "this quote has already been turned into an invoice"
    ) as twice:
        converted.mark_converted(new_id(), NOW)
    assert twice.value.code == "already_converted"
    with raises_exactly(InvalidStateError, "a declined quote cannot be turned into an invoice"):
        quote.decline(NOW).mark_converted(invoice_id, NOW)
    with raises_exactly(InvalidStateError, "a draft quote cannot be turned into an invoice"):
        draft(DocumentType.QUOTE).mark_converted(invoice_id, NOW)
    with raises_exactly(InvalidStateError, "only quotes can be turned into invoices"):
        issued().mark_converted(invoice_id, NOW)


def test_copy_as_draft_resets_dates_and_rates() -> None:
    quote = issued(DocumentType.QUOTE, subject="Website")
    invoice_id = new_id()
    invoice = quote.copy_as_draft(invoice_id, DocumentType.INVOICE, NOW + timedelta(days=1))
    assert invoice.id == invoice_id
    assert invoice.type is DocumentType.INVOICE
    assert invoice.is_draft
    assert invoice.source_id == quote.id
    assert invoice.content.subject == "Website"
    assert invoice.content.issue_date is None
    assert invoice.content.due_date is None
    assert all(line.tax_rate is None for line in invoice.content.lines)
    copied_ids = [line.id for line in invoice.content.lines]
    assert all(isinstance(line_id, UUID) for line_id in copied_ids)
    assert set(copied_ids).isdisjoint(line.id for line in quote.content.lines)
    assert invoice.events == (
        DocumentEvent(NOW + timedelta(days=1), EventKind.CREATED_FROM, "R20260001"),
    )
    assert invoice.created_at == NOW + timedelta(days=1)
    source = draft()
    duplicate = source.copy_as_draft(new_id(), DocumentType.INVOICE, NOW)
    assert duplicate.source_id is None
    assert duplicate.events[0].detail == str(source.id)


def test_display_status() -> None:
    quote = issued(DocumentType.QUOTE)
    assert quote.display_status(TODAY) is DisplayStatus.SENT
    assert quote.display_status(TODAY + timedelta(days=31)) is DisplayStatus.EXPIRED
    invoice = issued()
    assert invoice.display_status(TODAY + timedelta(days=30)) is DisplayStatus.ISSUED
    assert invoice.display_status(TODAY + timedelta(days=31)) is DisplayStatus.OVERDUE
    partially = pay(invoice, "100")
    assert partially.display_status(TODAY + timedelta(days=31)) is DisplayStatus.OVERDUE
    assert partially.display_status(TODAY) is DisplayStatus.PARTIALLY_PAID
    assert draft().display_status(TODAY + timedelta(days=999)) is DisplayStatus.DRAFT
    assert (
        pay(invoice, str(invoice.open_amount().amount)).display_status(
            TODAY + timedelta(days=99),
        )
        is DisplayStatus.PAID
    )


# --- Payments ---------------------------------------------------------------------------


def test_payments_change_the_status() -> None:
    invoice = issued()
    total = invoice.open_amount()
    partially = pay(invoice, "1000")
    assert partially.status is DocumentStatus.PARTIALLY_PAID
    assert partially.paid_amount == Money(Decimal(1000), Currency.CHF)
    assert partially.open_amount() == total - Money(Decimal(1000), Currency.CHF)
    assert partially.events[-1].kind is EventKind.PAYMENT_ADDED
    assert partially.events[-1].detail == "1000.00"
    paid = pay(partially, str(partially.open_amount().amount))
    assert paid.status is DocumentStatus.PAID
    assert paid.open_amount() == Money.zero(Currency.CHF)

    reopened = paid.remove_payment(paid.payments[1].id, LATER)
    assert reopened.status is DocumentStatus.PARTIALLY_PAID
    assert reopened.events[-1] == DocumentEvent(LATER, EventKind.PAYMENT_REMOVED, "659.50")
    unpaid = reopened.remove_payment(reopened.payments[0].id, NOW)
    assert unpaid.status is DocumentStatus.ISSUED
    assert unpaid.payments == ()


def test_payment_rules() -> None:
    invoice = issued()
    with raises_exactly(
        ValidationError, "the payment exceeds the open amount of CHF 1659.50"
    ) as exceeded:
        pay(invoice, "1659.55")
    assert exceeded.value.field == "amount"
    with raises_exactly(ValidationError, "the payment must be in CHF") as currency:
        invoice.add_payment(
            Payment(
                id=new_id(), paid_on=TODAY, amount=Money(Decimal(1), Currency.EUR), recorded_at=NOW
            ),
            NOW,
        )
    assert currency.value.field == "amount"
    with raises_exactly(InvalidStateError, "a draft invoice cannot be paid"):
        pay(draft(), "1")
    cancellation = replace(issued(), type=DocumentType.CANCELLATION)
    with raises_exactly(InvalidStateError, "only invoices are paid"):
        pay(cancellation, "1")
    with raises_exactly(InvalidStateError, "only invoices are paid"):
        cancellation.pay_in_full(new_id(), TODAY, NOW)
    with raises_exactly(InvalidStateError, "a issued invoice cannot be changed"):
        invoice.remove_payment(new_id(), NOW)
    with raises_exactly(ValidationError, "this payment does not belong to the document") as other:
        pay(invoice, "1").remove_payment(new_id(), NOW)
    assert other.value.field == "payment"
    for amount, message in [
        ("0", "a payment must be a positive amount"),
        ("-1", "a payment must be a positive amount"),
        ("1.001", "a payment has at most two decimal places"),
    ]:
        with raises_exactly(ValidationError, message) as error:
            Payment(
                id=new_id(),
                paid_on=TODAY,
                amount=Money(Decimal(amount), Currency.CHF),
                recorded_at=NOW,
            )
        assert error.value.field == "amount"
    note = Payment(
        id=new_id(),
        paid_on=TODAY,
        amount=Money(Decimal(1), Currency.CHF),
        recorded_at=NOW,
        note=" Bank ",
    )
    assert note.note == "Bank"
    with raises_exactly(ValidationError, "note must be at most 500 characters long") as long:
        Payment(
            id=new_id(),
            paid_on=TODAY,
            amount=Money(Decimal(1), Currency.CHF),
            recorded_at=NOW,
            note="x" * 501,
        )
    assert long.value.field == "note"


# --- Cancellation ------------------------------------------------------------------------------


def test_cancellation_negates_the_invoice() -> None:
    invoice = issued(
        discount=Discount.none(),
        intro_text="Wir stellen in Rechnung:",
        payment_text="Zahlbar bis {faellig}.",
        closing_text="Danke",
    )
    cancellation_draft = invoice.cancellation_draft(new_id(), NOW)
    assert cancellation_draft.type is DocumentType.CANCELLATION
    assert cancellation_draft.content.issue_date is None
    assert cancellation_draft.content.due_date is None
    # No request to pay on a cancellation; the closing words stay.
    assert cancellation_draft.content.intro_text == ""
    assert cancellation_draft.content.payment_text == ""
    assert cancellation_draft.content.closing_text == "Danke"
    negated_ids = [line.id for line in cancellation_draft.content.lines]
    assert all(isinstance(line_id, UUID) for line_id in negated_ids)
    assert set(negated_ids).isdisjoint(line.id for line in invoice.content.lines)
    assert cancellation_draft.source_id == invoice.id
    assert cancellation_draft.events[0].detail == "R20260001"
    assert [line.quantity for line in cancellation_draft.content.lines] == [
        Decimal(-10),
        Decimal(-3),
    ]
    # The invoice's rates are kept, so the cancellation reverses it exactly.
    assert [line.tax_rate for line in cancellation_draft.content.lines] == [
        line.tax_rate for line in invoice.content.lines
    ]
    cancellation = cancellation_draft.issue(
        number="S20260001",
        issue_date=TODAY,
        due_date=TODAY,
        snapshot=snapshot(),
        now=NOW,
    )
    assert cancellation.status is DocumentStatus.ISSUED
    # Due on the issue date, but a cancellation settles its invoice: never overdue.
    assert cancellation.display_status(TODAY + timedelta(days=99)) is DisplayStatus.ISSUED
    assert invoice.issued_totals is not None
    assert cancellation.issued_totals is not None
    assert cancellation.issued_totals.total == -invoice.issued_totals.total
    cancelled = invoice.cancel(cancellation, NOW)
    assert cancelled.status is DocumentStatus.CANCELLED
    assert cancelled.cancelled_by_id == cancellation.id
    assert cancelled.events[-1].kind is EventKind.CANCELLED
    assert cancelled.events[-1].detail == "S20260001"
    assert cancelled.open_amount() == Money.zero(Currency.CHF)


def test_text_lines_are_kept_in_cancellations() -> None:
    text = DocumentLine(id=new_id(), kind=LineKind.TEXT, description="Hinweis")
    cancellation = issued(lines=(text, line())).cancellation_draft(new_id(), NOW)
    kept = cancellation.content.lines[0]
    assert isinstance(kept.id, UUID)
    assert kept.id != text.id
    assert replace(kept, id=text.id) == text


def test_cancellation_rules() -> None:
    with raises_exactly(InvalidStateError, "a draft invoice cannot be cancelled"):
        draft().cancellation_draft(new_id(), NOW)
    with raises_exactly(InvalidStateError, "only invoices can be cancelled"):
        issued(DocumentType.QUOTE).cancel_check()
    invoice = issued()
    other = issued().cancellation_draft(new_id(), NOW)
    with raises_exactly(InvalidStateError, "the cancellation does not belong to this invoice"):
        invoice.cancel(other, NOW)
    paid = pay(invoice, str(invoice.open_amount().amount))
    paid.cancel_check()
    partially = pay(invoice, "1")
    partially.cancel_check()
    cancellation = invoice.cancellation_draft(new_id(), NOW).issue(
        number="S1", issue_date=TODAY, due_date=TODAY, snapshot=snapshot(), now=NOW
    )
    with raises_exactly(InvalidStateError, "a cancelled invoice cannot be cancelled"):
        invoice.cancel(cancellation, NOW).cancel_check()
    assert cancellation.issued_totals is not None
    tampered = replace(
        cancellation,
        issued_totals=replace(
            cancellation.issued_totals,
            total=cancellation.issued_totals.total + Money(Decimal("0.05"), Currency.CHF),
        ),
    )
    with raises_exactly(InvalidStateError, "the cancellation must reverse the invoice exactly"):
        invoice.cancel(tampered, NOW)
    with raises_exactly(InvalidStateError, "the cancellation must reverse the invoice exactly"):
        invoice.cancel(invoice.cancellation_draft(new_id(), NOW), NOW)


@pytest.mark.parametrize(
    ("country", "invoice_date", "cancellation_date", "rates"),
    [
        # CH: 7.7 % / 2.5 % until 2023-12-31, then 8.1 % / 2.6 %.
        ("CH", date(2023, 12, 20), date(2024, 1, 5), [Decimal("7.7"), Decimal("2.5")]),
        # DE: temporary 16 % / 5 % from 2020-07-01 to 2020-12-31.
        ("DE", date(2020, 12, 20), date(2021, 1, 5), [Decimal(16), Decimal(5)]),
    ],
)
def test_a_cancellation_keeps_the_rates_of_its_invoice(
    country: str, invoice_date: date, cancellation_date: date, rates: list[Decimal]
) -> None:
    company = factories.company(address=factories.address(country=CountryCode(country)))
    parties = replace(snapshot(), company=company)
    invoice = draft().issue(
        number="R1", issue_date=invoice_date, due_date=invoice_date, snapshot=parties, now=NOW
    )
    assert [line.tax_rate for line in invoice.content.lines] == rates
    cancellation = invoice.cancellation_draft(new_id(), NOW).issue(
        number="S1",
        issue_date=cancellation_date,
        due_date=cancellation_date,
        snapshot=parties,
        now=NOW,
    )
    assert [line.tax_rate for line in cancellation.content.lines] == rates
    assert invoice.issued_totals is not None
    assert cancellation.issued_totals is not None
    assert cancellation.issued_totals.total == -invoice.issued_totals.total
    assert invoice.cancel(cancellation, NOW).status is DocumentStatus.CANCELLED


def test_drafts_have_no_snapshot() -> None:
    with raises_exactly(InvalidStateError, "the document has not been issued yet"):
        _ = draft().issued_snapshot


def test_default_due_dates() -> None:
    assert default_due_date(DocumentType.INVOICE, TODAY, 10) == TODAY + timedelta(days=10)
    assert default_due_date(DocumentType.QUOTE, TODAY, 10) == TODAY + timedelta(days=30)
    assert default_due_date(DocumentType.CANCELLATION, TODAY, 10) == TODAY


def test_issuing_checks_the_mandatory_information_of_invoices() -> None:
    unregistered = IssueSnapshot(
        company=factories.company(vat_number=None),
        customer=factories.customer(),
        bank_account=None,
    )
    with raises_exactly(
        ValidationError, "VAT registered companies state their VAT number (UID) on invoices"
    ) as error:
        draft().issue(number="R1", issue_date=TODAY, due_date=TODAY, snapshot=unregistered, now=NOW)
    assert error.value.code == "company_vat_number_missing"
    # Quotes are no invoices.
    quote = draft(DocumentType.QUOTE).issue(
        number="A1", issue_date=TODAY, due_date=TODAY, snapshot=unregistered, now=NOW
    )
    assert quote.status is DocumentStatus.SENT
    # Cancellations repeat the parties of their invoice, even when those lack something.
    invoice = issued()
    cancellation = invoice.cancellation_draft(new_id(), NOW).issue(
        number="S1", issue_date=TODAY, due_date=TODAY, snapshot=unregistered, now=NOW
    )
    assert cancellation.status is DocumentStatus.ISSUED


def test_mails_are_recorded_in_the_history() -> None:
    invoice = issued()
    mailed = invoice.record_mail(EventKind.EMAILED, "anna@example.com", LATER)
    assert mailed.events[-1] == DocumentEvent(LATER, EventKind.EMAILED, "anna@example.com")
    assert mailed.status is invoice.status
    reminded = invoice.record_mail(EventKind.REMINDER_EMAILED, "2 " + "x" * 600, LATER)
    assert len(reminded.events[-1].detail) == 500
    with raises_exactly(InvalidStateError, "drafts are not sent; issue the document first"):
        draft().record_mail(EventKind.EMAILED, "a@example.com", LATER)
    with raises_exactly(ValidationError, "only mails are recorded this way"):
        invoice.record_mail(EventKind.PAYMENT_ADDED, "x", LATER)


def test_issue_blockers_name_all_missing_party_details_at_once() -> None:
    german = factories.company(
        address=factories.address(country=CountryCode("DE")), vat_number=None, tax_number=""
    )
    customer = factories.customer(address=factories.address(country=CountryCode("AT")))
    supply = draft(
        lines=(line("1", "300.00", supply=Supply.GOODS),),
        currency=Currency.EUR,
        treatment=TaxTreatment.REVERSE_CHARGE,
        goods_treatment=TaxTreatment.INTRA_COMMUNITY,
    )
    assert supply.issue_blockers(german, customer, Money(Decimal(300), Currency.EUR)) == (
        "reverse_charge_needs_vat_number",
        "company_tax_id_missing",
        "company_vat_id_missing",
        "customer_vat_id_missing",
    )


def test_issue_blockers_are_empty_when_the_details_are_complete() -> None:
    total = Money(Decimal(1500), Currency.CHF)
    assert draft().issue_blockers(factories.company(), factories.customer(), total) == ()
    swiss = factories.company(vat_number=None)
    assert draft().issue_blockers(swiss, factories.customer(), total) == (
        "company_vat_number_missing",
    )
    # Quotes are sent, not issued: they state no tax IDs.
    assert draft(DocumentType.QUOTE).issue_blockers(swiss, factories.customer(), total) == ()
