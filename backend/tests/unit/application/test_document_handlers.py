from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from rhinvoice.application.common import PageRequest
from rhinvoice.application.document.handlers import (
    DocumentHandlers,
    DraftInput,
    LineInput,
    PaymentInput,
    RecordedPayment,
    build_index,
)
from rhinvoice.application.document.ports import DocumentQuery
from rhinvoice.application.errors import NotFoundError
from rhinvoice.domain.customer.customer import CustomerKind
from rhinvoice.domain.document.document import (
    DisplayStatus,
    DocumentEvent,
    DocumentStatus,
    DocumentType,
    EventKind,
)
from rhinvoice.domain.document.lines import DiscountKind, LineKind, PriceMode
from rhinvoice.domain.numbering.sequence import SequenceKind
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.country import CountryCode
from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency, Money
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply
from rhinvoice.domain.tax.treatment import TaxTreatment
from rhinvoice.domain.tax.vat_number import VatNumber
from rhinvoice.domain.text.template import TextKind, TextTemplate
from tests.helpers import raises_exactly
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories

TODAY = NOW.date()


@pytest.fixture
def units() -> list[InMemoryUnitOfWork]:
    """Every unit of work the handlers opened, in order."""
    return []


@pytest.fixture
def handlers(store: Store, clock: FixedClock, units: list[InMemoryUnitOfWork]) -> DocumentHandlers:
    company = factories.company(payment_terms_days=30)
    store.company = company
    account = factories.bank_account(is_default=True)
    store.bank_accounts[account.id] = account
    customer = factories.customer(id=UUID(int=1), payment_terms_days=None)
    store.customers[customer.id] = customer

    def unit_of_work() -> InMemoryUnitOfWork:
        uow = InMemoryUnitOfWork(store)
        units.append(uow)
        return uow

    return DocumentHandlers(uow=unit_of_work, clock=clock)


CUSTOMER = UUID(int=1)
HOURS = LineInput(
    kind=LineKind.ITEM, description="Beratung", quantity="10", unit="HUR", unit_price="150"
)
FOOD = LineInput(
    kind=LineKind.ITEM,
    description="Kaffee",
    quantity="3",
    unit="C62",
    unit_price="12.35",
    tax_category=TaxCategory.REDUCED,
)


def draft_input(**overrides: object) -> DraftInput:
    values: dict[str, object] = {"customer_id": CUSTOMER, "lines": (HOURS, FOOD)}
    values.update(overrides)
    return DraftInput(**values)  # type: ignore[arg-type]  # test builder


def test_create_uses_customer_and_company_defaults(
    handlers: DocumentHandlers, store: Store
) -> None:
    customer = store.customers[CUSTOMER]
    store.customers[CUSTOMER] = replace(
        customer,
        default_currency=Currency.EUR,
        default_language=Language.EN,
        default_discount=Decimal("2.5"),
    )
    view = handlers.create(DocumentType.INVOICE, draft_input())
    document = view.document
    assert document.content.currency is Currency.EUR
    assert document.content.language is Language.EN
    assert document.content.discount.value == Decimal("2.5")
    assert document.content.treatment is TaxTreatment.DOMESTIC
    assert view.display_status is DisplayStatus.DRAFT
    assert view.customer == store.customers[CUSTOMER]
    assert view.totals.subtotal == Money(Decimal("1537.05"), Currency.EUR)
    assert all(isinstance(line.id, UUID) for line in document.content.lines)
    stored = store.documents[document.id]
    assert stored.index.customer_name == "Beispiel AG"
    assert stored.index.total == view.totals.total


def test_create_falls_back_to_company_defaults(handlers: DocumentHandlers) -> None:
    view = handlers.create(DocumentType.QUOTE, draft_input())
    document = view.document
    # The company rounds CHF to 0.05: 1659.51 -> 1659.50.
    assert view.totals.total == Money(Decimal("1659.50"), Currency.CHF)
    assert document.type is DocumentType.QUOTE
    assert document.content.currency is Currency.CHF
    assert document.content.language is Language.DE
    assert document.content.discount.value == 0


def test_create_requires_company_and_customer(handlers: DocumentHandlers, store: Store) -> None:
    with raises_exactly(ValidationError, "the customer does not exist") as customer:
        handlers.create(DocumentType.INVOICE, draft_input(customer_id=new_id()))
    assert customer.value.field == "customer_id"
    store.company = None
    with raises_exactly(
        ValidationError, "please set up the company before creating documents"
    ) as company:
        handlers.create(DocumentType.INVOICE, draft_input())
    assert company.value.field == "company"


def test_line_errors_name_the_line(handlers: DocumentHandlers) -> None:
    broken = replace(FOOD, quantity="abc")
    with pytest.raises(ValidationError) as error:
        handlers.create(DocumentType.INVOICE, draft_input(lines=(HOURS, broken)))
    assert error.value.field == "lines.1.quantity"
    with pytest.raises(ValidationError) as unit:
        handlers.create(DocumentType.INVOICE, draft_input(lines=(replace(HOURS, unit="XYZ"),)))
    assert unit.value.field == "lines.0.unit"
    for field, invalid in [
        ("unit_price", replace(HOURS, unit_price="abc")),
        ("discount_percent", replace(HOURS, discount_percent="abc")),
    ]:
        with raises_exactly(ValidationError, "'abc' is not a valid number") as error:
            handlers.create(DocumentType.INVOICE, draft_input(lines=(invalid,)))
        assert error.value.field == f"lines.0.{field}"


def test_line_input_is_taken_over(handlers: DocumentHandlers) -> None:
    article_id = new_id()
    line = replace(HOURS, details="Juni", discount_percent="10", article_id=article_id)
    document = handlers.create(DocumentType.INVOICE, draft_input(lines=(line,))).document
    created = document.content.lines
    assert (created[0].details, created[0].discount_percent, created[0].article_id) == (
        "Juni",
        Decimal(10),
        article_id,
    )


def test_text_lines_have_no_unit(handlers: DocumentHandlers) -> None:
    text = LineInput(kind=LineKind.TEXT, description="Phase 1", unit="HUR")
    no_unit = replace(HOURS, unit=None)
    document = handlers.create(DocumentType.INVOICE, draft_input(lines=(text, no_unit))).document
    assert [line.unit for line in document.content.lines] == [None, None]


def test_treatment_is_determined_and_can_be_overridden(
    handlers: DocumentHandlers, store: Store
) -> None:
    foreign = factories.customer(
        id=UUID(int=2), address=factories.address(country=CountryCode("DE"))
    )
    store.customers[foreign.id] = foreign
    export = handlers.create(DocumentType.INVOICE, draft_input(customer_id=foreign.id)).document
    assert export.content.treatment is TaxTreatment.EXPORT
    overridden = handlers.create(
        DocumentType.INVOICE,
        draft_input(treatment_override=TaxTreatment.DOMESTIC, override_reason="Leistung in CH"),
    ).document
    assert overridden.content.treatment_overridden
    assert overridden.events[-1].kind is EventKind.TAX_OVERRIDDEN
    assert overridden.events[-1].detail == "domestic: Leistung in CH"


def test_treatment_depends_on_company_and_customer(
    handlers: DocumentHandlers, store: Store
) -> None:
    def treatment() -> TaxTreatment:
        return handlers.create(DocumentType.INVOICE, draft_input()).document.content.treatment

    company = store.company
    assert company is not None
    customer = store.customers[CUSTOMER]
    store.company = replace(company, address=factories.address(country=CountryCode("DE")))
    austrian = factories.address(country=CountryCode("AT"))
    store.customers[CUSTOMER] = replace(customer, address=austrian)
    assert treatment() is TaxTreatment.DOMESTIC
    store.customers[CUSTOMER] = replace(
        customer, address=austrian, vat_number=VatNumber.parse("ATU12345678")
    )
    assert treatment() is TaxTreatment.REVERSE_CHARGE
    store.customers[CUSTOMER] = replace(
        customer,
        kind=CustomerKind.PERSON,
        company_name="",
        first_name="Anna",
        last_name="Muster",
        address=austrian,
        vat_number=VatNumber.parse("ATU12345678"),
    )
    assert treatment() is TaxTreatment.DOMESTIC
    store.customers[CUSTOMER] = replace(customer, tax_exempt=True)
    assert treatment() is TaxTreatment.EXEMPT
    store.company = replace(company, small_business=True)
    assert treatment() is TaxTreatment.SMALL_BUSINESS


def test_draft_input_is_taken_over(handlers: DocumentHandlers) -> None:
    content = handlers.create(
        DocumentType.INVOICE,
        draft_input(
            service_from=date(2026, 2, 1),
            service_to=date(2026, 2, 28),
            intro_text="Hallo",
            closing_text="Danke",
        ),
    ).document.content
    assert (content.service_from, content.service_to) == (date(2026, 2, 1), date(2026, 2, 28))
    assert (content.intro_text, content.closing_text) == ("Hallo", "Danke")
    with raises_exactly(ValidationError, "'viel' is not a valid number") as error:
        handlers.create(DocumentType.INVOICE, draft_input(discount_value="viel"))
    assert error.value.field == "discount"


def test_update_keeps_the_discount_unless_given(handlers: DocumentHandlers) -> None:
    created = handlers.create(DocumentType.INVOICE, draft_input(discount_value="5")).document
    updated = handlers.update(created.id, draft_input(subject="Neu")).document
    assert updated.content.discount.value == 5
    assert updated.content.subject == "Neu"
    amount = handlers.update(
        created.id,
        draft_input(
            discount_kind=DiscountKind.AMOUNT, discount_value="10", price_mode=PriceMode.GROSS
        ),
    ).document
    assert amount.content.discount.kind is DiscountKind.AMOUNT
    assert amount.content.price_mode is PriceMode.GROSS
    with raises_exactly(NotFoundError, "document not found"):
        handlers.update(new_id(), draft_input())


def test_update_logs_a_tax_override(handlers: DocumentHandlers) -> None:
    created = handlers.create(DocumentType.INVOICE, draft_input()).document
    updated = handlers.update(
        created.id,
        draft_input(treatment_override=TaxTreatment.EXPORT, override_reason="Ausfuhr"),
    ).document
    assert updated.events[-1] == DocumentEvent(NOW, EventKind.TAX_OVERRIDDEN, "export: Ausfuhr")


def test_issue_assigns_number_dates_and_snapshot(handlers: DocumentHandlers, store: Store) -> None:
    created = handlers.create(DocumentType.INVOICE, draft_input()).document
    view = handlers.issue(created.id)
    document = view.document
    assert document.status is DocumentStatus.ISSUED
    assert document.number == "R20260001"
    assert document.content.issue_date == TODAY
    assert document.content.due_date == TODAY + timedelta(days=30)
    assert document.snapshot is not None
    assert document.snapshot.customer == store.customers[CUSTOMER]
    assert document.snapshot.bank_account is not None
    assert store.sequences[SequenceKind.INVOICE].next_value == 2
    assert store.documents[document.id].index.open_amount == view.totals.total
    assert store.documents[document.id].index.search_text == "R20260001 Beispiel AG Beratung Kaffee"
    assert view.display_status is DisplayStatus.ISSUED


def test_issue_uses_customer_terms_and_given_dates(
    handlers: DocumentHandlers, store: Store
) -> None:
    store.customers[CUSTOMER] = replace(store.customers[CUSTOMER], payment_terms_days=10)
    dated = handlers.create(
        DocumentType.INVOICE,
        draft_input(issue_date=date(2026, 3, 1), due_date=date(2026, 3, 20)),
    ).document
    issued = handlers.issue(dated.id).document
    assert (issued.content.issue_date, issued.content.due_date) == (
        date(2026, 3, 1),
        date(2026, 3, 20),
    )
    assert issued.number == "R20260001"
    created = handlers.create(DocumentType.INVOICE, draft_input()).document
    assert handlers.issue(created.id).document.content.due_date == TODAY + timedelta(days=10)
    quote = handlers.create(DocumentType.QUOTE, draft_input()).document
    assert handlers.issue(quote.id).document.content.due_date == TODAY + timedelta(days=30)


def test_invoices_need_a_bank_account_in_their_currency(
    handlers: DocumentHandlers, store: Store
) -> None:
    created = handlers.create(DocumentType.INVOICE, draft_input(currency=Currency.EUR)).document
    with raises_exactly(
        ValidationError, "please add a bank account for EUR before issuing invoices in EUR"
    ) as error:
        handlers.issue(created.id)
    assert error.value.field == "currency"
    assert SequenceKind.INVOICE not in store.sequences
    quote = handlers.create(DocumentType.QUOTE, draft_input(currency=Currency.EUR)).document
    sent = handlers.issue(quote.id).document
    assert sent.status is DocumentStatus.SENT
    assert sent.number == "A20260001"
    assert sent.snapshot is not None
    assert sent.snapshot.bank_account is None
    assert sent.content.due_date == TODAY + timedelta(days=30)


def test_quote_accept_decline_and_convert(handlers: DocumentHandlers, store: Store) -> None:
    quote = handlers.issue(handlers.create(DocumentType.QUOTE, draft_input()).document.id).document
    accepted = handlers.accept(quote.id).document
    assert accepted.status is DocumentStatus.ACCEPTED
    assert accepted.events[-1] == DocumentEvent(NOW, EventKind.ACCEPTED, "")
    other = handlers.issue(handlers.create(DocumentType.QUOTE, draft_input()).document.id).document
    declined = handlers.decline(other.id).document
    assert declined.status is DocumentStatus.DECLINED
    assert declined.events[-1] == DocumentEvent(NOW, EventKind.DECLINED, "")
    with raises_exactly(InvalidStateError, "a declined quote cannot be turned into an invoice"):
        handlers.convert_to_invoice(other.id)
    invoice = handlers.convert_to_invoice(quote.id).document
    assert isinstance(invoice.id, UUID)
    assert invoice.type is DocumentType.INVOICE
    assert invoice.is_draft
    assert invoice.source_id == quote.id
    # Dated today like a new invoice; due as the terms say when issued.
    assert (invoice.content.issue_date, invoice.content.due_date) == (TODAY, None)
    converted = store.documents[quote.id].document
    assert converted.converted_to_id == invoice.id
    assert converted.events[-1] == DocumentEvent(NOW, EventKind.CONVERTED, str(invoice.id))
    with raises_exactly(
        InvalidStateError, "this quote has already been turned into an invoice"
    ) as twice:
        handlers.convert_to_invoice(quote.id)
    assert twice.value.code == "already_converted"


def test_duplicate(handlers: DocumentHandlers) -> None:
    invoice = handlers.issue(
        handlers.create(DocumentType.INVOICE, draft_input(subject="A")).document.id
    )
    copy = handlers.duplicate(invoice.document.id).document
    assert copy.is_draft
    assert copy.type is DocumentType.INVOICE
    assert copy.content.subject == "A"
    assert (copy.content.issue_date, copy.content.due_date) == (TODAY, None)
    assert isinstance(copy.id, UUID)
    assert copy.id != invoice.document.id


def test_delete_only_drafts(handlers: DocumentHandlers, store: Store) -> None:
    draft = handlers.create(DocumentType.INVOICE, draft_input()).document
    issued = handlers.issue(
        handlers.create(DocumentType.INVOICE, draft_input()).document.id
    ).document
    handlers.delete(draft.id)
    assert draft.id not in store.documents
    with raises_exactly(InvalidStateError, "a issued invoice cannot be deleted"):
        handlers.delete(issued.id)
    assert issued.id in store.documents


def test_cancel_issues_a_cancellation(handlers: DocumentHandlers, store: Store) -> None:
    invoice = handlers.issue(
        handlers.create(DocumentType.INVOICE, draft_input()).document.id
    ).document
    view = handlers.cancel(invoice.id)
    cancelled = view.document
    assert cancelled.status is DocumentStatus.CANCELLED
    assert cancelled.cancelled_by_id is not None
    cancellation = store.documents[cancelled.cancelled_by_id].document
    assert cancellation.type is DocumentType.CANCELLATION
    assert cancellation.number == "S20260001"
    assert cancellation.content.due_date == TODAY
    assert cancellation.source_id == invoice.id
    assert cancellation.issued_totals is not None
    assert invoice.issued_totals is not None
    assert cancellation.issued_totals.total == -invoice.issued_totals.total
    assert cancelled.events[-1].detail == "S20260001"
    with raises_exactly(InvalidStateError, "cancellation invoices cannot be duplicated"):
        handlers.duplicate(cancellation.id)


def test_a_cancellation_uses_the_parties_and_rounding_of_its_invoice(
    handlers: DocumentHandlers, store: Store
) -> None:
    invoice = handlers.issue(
        handlers.create(DocumentType.INVOICE, draft_input()).document.id
    ).document
    # Master data changes after issuing must not change the reversal.
    assert store.company is not None
    store.company = replace(store.company, name="Neue Firma AG", cash_rounding=False)
    store.customers[CUSTOMER] = replace(store.customers[CUSTOMER], company_name="Umbenannt AG")
    cancelled = handlers.cancel(invoice.id).document
    assert cancelled.cancelled_by_id is not None
    cancellation = store.documents[cancelled.cancelled_by_id].document
    original = invoice.issued_snapshot
    assert cancellation.issued_snapshot == replace(original, bank_account=None)
    assert cancellation.issued_totals is not None
    assert invoice.issued_totals is not None
    assert cancellation.issued_totals.total == -invoice.issued_totals.total


def test_issue_rules(handlers: DocumentHandlers, clock: FixedClock) -> None:
    future = handlers.create(
        DocumentType.INVOICE, draft_input(issue_date=TODAY + timedelta(days=1))
    )
    with raises_exactly(ValidationError, "the document date is in the future") as error:
        handlers.issue(future.document.id)
    assert (error.value.field, error.value.code) == ("issue_date", "issue_date_in_future")
    handlers.issue(handlers.create(DocumentType.INVOICE, draft_input()).document.id)
    backdated = handlers.create(
        DocumentType.INVOICE, draft_input(issue_date=TODAY - timedelta(days=1))
    )
    with raises_exactly(
        ValidationError, "the document date is before the last issued document (2026-03-09)"
    ) as before:
        handlers.issue(backdated.document.id)
    assert before.value.code == "issue_date_before_last"
    # Other document types have their own order.
    handlers.issue(
        handlers.create(
            DocumentType.QUOTE, draft_input(issue_date=TODAY - timedelta(days=5))
        ).document.id
    )
    # The number follows the document date, not the day of issuing.
    clock.set(datetime(2027, 1, 2, 9, 0, tzinfo=UTC))
    late = handlers.create(DocumentType.INVOICE, draft_input(issue_date=date(2026, 12, 30)))
    assert handlers.issue(late.document.id).document.number == "R20260002"
    empty = handlers.create(
        DocumentType.INVOICE, draft_input(lines=(replace(HOURS, unit_price="0"),))
    )
    with raises_exactly(ValidationError, "the total of an invoice must be positive") as zero:
        handlers.issue(empty.document.id)
    assert zero.value.code == "non_positive_total"
    with raises_exactly(
        ValidationError, "the document needs at least one position with an amount"
    ) as nothing:
        handlers.issue(handlers.create(DocumentType.INVOICE, draft_input(lines=())).document.id)
    assert nothing.value.code == "no_positions"


def test_issue_determines_the_tax_treatment_again(handlers: DocumentHandlers, store: Store) -> None:
    created = handlers.create(DocumentType.INVOICE, draft_input()).document
    assert created.content.treatment is TaxTreatment.DOMESTIC
    # The customer moved abroad after the draft was saved.
    store.customers[CUSTOMER] = replace(
        store.customers[CUSTOMER], address=factories.address(country=CountryCode("DE"))
    )
    issued = handlers.issue(created.id).document
    assert issued.content.treatment is TaxTreatment.EXPORT
    assert issued.issued_totals is not None
    assert issued.issued_totals.tax.is_zero
    overridden = handlers.create(
        DocumentType.INVOICE,
        draft_input(treatment_override=TaxTreatment.DOMESTIC, override_reason="Inland"),
    ).document
    assert handlers.issue(overridden.id).document.content.treatment is TaxTreatment.DOMESTIC


def test_reverse_charge_needs_the_customer_vat_number(handlers: DocumentHandlers) -> None:
    created = handlers.create(
        DocumentType.INVOICE,
        draft_input(treatment_override=TaxTreatment.REVERSE_CHARGE, override_reason="EU"),
    ).document
    with raises_exactly(ValidationError, "reverse charge needs the customer's VAT number") as error:
        handlers.issue(created.id)
    assert (error.value.field, error.value.code) == ("treatment", "reverse_charge_needs_vat_number")


def test_the_notice_follows_the_treatment_and_is_frozen_when_issued(
    handlers: DocumentHandlers, store: Store
) -> None:
    store.customers[CUSTOMER] = replace(
        store.customers[CUSTOMER],
        address=factories.address(country=CountryCode("AT")),
        vat_number=VatNumber.parse("ATU12345678"),
    )
    rc = (
        "Übergang der Steuerschuld auf den Leistungsempfänger "
        "(Steuerschuldnerschaft des Leistungsempfängers, Reverse Charge)."
    )
    draft = handlers.create(
        DocumentType.INVOICE, draft_input(currency=Currency.CHF, payment_text=" Sofort. ")
    )
    assert draft.document.content.treatment is TaxTreatment.REVERSE_CHARGE
    assert draft.document.content.payment_text == "Sofort."
    assert draft.notice == rc
    # Drafts show the wording of today.
    store.legal_notices[TaxTreatment.REVERSE_CHARGE, Language.DE] = "Eigener Hinweis."
    assert handlers.get(draft.document.id).notice == "Eigener Hinweis."
    issued = handlers.issue(draft.document.id)
    assert issued.document.issued_snapshot.notice == "Eigener Hinweis."
    # Issued documents keep the wording they were issued with, also their cancellation.
    store.legal_notices.clear()
    assert handlers.get(draft.document.id).notice == "Eigener Hinweis."
    cancellation = handlers.cancel(draft.document.id).document.cancelled_by_id
    assert cancellation is not None
    assert handlers.get(cancellation).notice == "Eigener Hinweis."
    # The notice of a draft follows its saved treatment, not the customer of today.
    later = handlers.create(DocumentType.INVOICE, draft_input(currency=Currency.CHF))
    store.customers[CUSTOMER] = replace(store.customers[CUSTOMER], vat_number=None)
    assert handlers.get(later.document.id).notice == rc
    plain = handlers.create(
        DocumentType.INVOICE,
        draft_input(treatment_override=TaxTreatment.DOMESTIC, override_reason="Test"),
    )
    assert plain.notice == ""


PRINTER = LineInput(
    kind=LineKind.ITEM, description="Drucker", quantity="1", unit_price="400", supply=Supply.GOODS
)
EXPORT_GOODS = "Steuerbefreite Ausfuhrlieferung (Art. 23 Abs. 2 Ziff. 1 MWSTG)."


def test_goods_get_their_own_treatment_and_notice(handlers: DocumentHandlers, store: Store) -> None:
    store.customers[CUSTOMER] = replace(
        store.customers[CUSTOMER],
        address=factories.address(country=CountryCode("AT")),
        vat_number=VatNumber.parse("ATU12345678"),
    )
    draft = handlers.create(DocumentType.INVOICE, draft_input(lines=(HOURS, PRINTER)))
    content = draft.document.content
    # From Switzerland the service is reverse charge, the printer an export.
    assert (content.treatment, content.goods_treatment) == (
        TaxTreatment.REVERSE_CHARGE,
        TaxTreatment.GOODS_EXPORT,
    )
    assert [line.supply for line in content.lines] == [Supply.SERVICE, Supply.GOODS]
    assert [treatment for treatment, _ in draft.notices] == [
        TaxTreatment.REVERSE_CHARGE,
        TaxTreatment.GOODS_EXPORT,
    ]
    assert draft.notice_of(TaxTreatment.GOODS_EXPORT) == EXPORT_GOODS
    assert draft.notice_of(TaxTreatment.DOMESTIC) == ""
    assert draft.notice.endswith(f"Reverse Charge).\n{EXPORT_GOODS}")
    store.legal_notices[TaxTreatment.GOODS_EXPORT, Language.DE] = "Ausfuhr."
    issued = handlers.issue(draft.document.id)
    assert issued.document.issued_snapshot.goods_notice == "Ausfuhr."
    store.legal_notices.clear()
    assert handlers.get(draft.document.id).notice_of(TaxTreatment.GOODS_EXPORT) == "Ausfuhr."
    # Old documents without a frozen goods notice show today's wording.
    old = replace(
        issued.document,
        snapshot=replace(issued.document.issued_snapshot, goods_notice=None),
    )
    store.documents[old.id] = replace(store.documents[old.id], document=old)
    assert handlers.get(old.id).notice_of(TaxTreatment.GOODS_EXPORT) == EXPORT_GOODS
    # Only goods: only their notice.
    goods_only = handlers.create(DocumentType.INVOICE, draft_input(lines=(PRINTER,)))
    assert goods_only.notice == EXPORT_GOODS
    assert handlers.issue(goods_only.document.id).document.issued_snapshot.goods_notice == (
        EXPORT_GOODS
    )
    # Services only: no goods notice is frozen.
    services = handlers.create(DocumentType.INVOICE, draft_input(lines=(HOURS,)))
    assert handlers.issue(services.document.id).document.issued_snapshot.goods_notice is None


def test_goods_treatment_is_determined_again_when_issuing(
    handlers: DocumentHandlers, store: Store
) -> None:
    created = handlers.create(DocumentType.INVOICE, draft_input(lines=(PRINTER,))).document
    assert created.content.goods_treatment is TaxTreatment.DOMESTIC
    store.customers[CUSTOMER] = replace(
        store.customers[CUSTOMER], address=factories.address(country=CountryCode("US"))
    )
    issued = handlers.issue(created.id).document
    assert issued.content.goods_treatment is TaxTreatment.GOODS_EXPORT
    assert issued.issued_totals is not None
    assert issued.issued_totals.tax.is_zero
    # A treatment chosen by hand stays, for the goods in their form.
    chosen = handlers.create(
        DocumentType.INVOICE,
        draft_input(
            lines=(PRINTER,), treatment_override=TaxTreatment.DOMESTIC, override_reason="Abholung"
        ),
    ).document
    assert chosen.content.goods_treatment is TaxTreatment.DOMESTIC
    issued_chosen = handlers.issue(chosen.id).document
    assert issued_chosen.content.goods_treatment is TaxTreatment.DOMESTIC
    assert issued_chosen.issued_totals is not None
    assert not issued_chosen.issued_totals.tax.is_zero


def test_goods_go_where_they_are_delivered(handlers: DocumentHandlers, store: Store) -> None:
    store.customers[CUSTOMER] = replace(
        store.customers[CUSTOMER],
        address=factories.address(country=CountryCode("DE")),
        delivery_address=factories.address(country=CountryCode("LI")),
        vat_number=VatNumber.parse("DE123456789"),
    )
    content = handlers.create(DocumentType.INVOICE, draft_input(lines=(HOURS, PRINTER))).document
    # The service goes to the German business (reverse charge), the printer stays in the
    # Swiss VAT area and is taxed at home.
    assert (content.content.treatment, content.content.goods_treatment) == (
        TaxTreatment.REVERSE_CHARGE,
        TaxTreatment.DOMESTIC,
    )


def test_goods_treatments_cannot_be_chosen_for_a_document(handlers: DocumentHandlers) -> None:
    with raises_exactly(
        ValidationError, "goods get this treatment from reverse charge or an export"
    ):
        handlers.create(
            DocumentType.INVOICE,
            draft_input(treatment_override=TaxTreatment.GOODS_EXPORT, override_reason="x"),
        )


def test_documents_issued_before_notices_were_stored_show_todays_wording(
    handlers: DocumentHandlers, store: Store
) -> None:
    store.customers[CUSTOMER] = replace(
        store.customers[CUSTOMER],
        address=factories.address(country=CountryCode("AT")),
        vat_number=VatNumber.parse("ATU12345678"),
    )
    created = handlers.create(DocumentType.INVOICE, draft_input(currency=Currency.CHF))
    issued = handlers.issue(created.document.id).document
    old = replace(issued, snapshot=replace(issued.issued_snapshot, notice=None))
    store.documents[issued.id] = replace(store.documents[issued.id], document=old)
    assert handlers.get(issued.id).notice == (
        "Übergang der Steuerschuld auf den Leistungsempfänger "
        "(Steuerschuldnerschaft des Leistungsempfängers, Reverse Charge)."
    )


def test_payments_cannot_be_dated_in_the_future(handlers: DocumentHandlers) -> None:
    invoice = handlers.issue(
        handlers.create(DocumentType.INVOICE, draft_input()).document.id
    ).document
    tomorrow = TODAY + timedelta(days=1)
    with raises_exactly(ValidationError, "the payment date is in the future") as error:
        handlers.add_payment(invoice.id, PaymentInput(paid_on=tomorrow, amount="1"))
    assert error.value.code == "payment_date_in_future"
    with raises_exactly(ValidationError, "the payment date is in the future"):
        handlers.mark_paid(invoice.id, tomorrow)
    draft = handlers.create(DocumentType.INVOICE, draft_input()).document
    with raises_exactly(InvalidStateError, "a draft invoice cannot be paid"):
        handlers.mark_paid(draft.id, TODAY)


def test_refused_cancellations_do_not_use_up_numbers(
    handlers: DocumentHandlers, store: Store
) -> None:
    draft = handlers.create(DocumentType.INVOICE, draft_input()).document
    with raises_exactly(InvalidStateError, "a draft invoice cannot be cancelled"):
        handlers.cancel(draft.id)
    assert SequenceKind.CANCELLATION not in store.sequences


def test_payments(handlers: DocumentHandlers, store: Store) -> None:
    invoice = handlers.issue(
        handlers.create(DocumentType.INVOICE, draft_input()).document.id
    ).document
    partial = handlers.add_payment(
        invoice.id, PaymentInput(paid_on=date(2026, 3, 2), amount="1000", note="Teil")
    )
    assert partial.document.status is DocumentStatus.PARTIALLY_PAID
    first = partial.document.payments[0]
    assert isinstance(first.id, UUID)
    assert (first.paid_on, first.recorded_at, first.note) == (date(2026, 3, 2), NOW, "Teil")
    assert store.documents[invoice.id].index.open_amount == Money(Decimal("659.50"), Currency.CHF)
    paid = handlers.mark_paid(invoice.id, date(2026, 3, 5))
    assert paid.document.status is DocumentStatus.PAID
    rest = paid.document.payments[-1]
    assert isinstance(rest.id, UUID)
    assert rest.id != first.id
    assert (rest.paid_on, rest.recorded_at) == (date(2026, 3, 5), NOW)
    assert rest.amount == Money(Decimal("659.50"), Currency.CHF)
    assert store.documents[invoice.id].index.open_amount == Money.zero(Currency.CHF)
    removed = handlers.remove_payment(invoice.id, paid.document.payments[0].id)
    assert removed.document.status is DocumentStatus.PARTIALLY_PAID
    assert removed.document.events[-1] == DocumentEvent(NOW, EventKind.PAYMENT_REMOVED, "1000.00")
    with raises_exactly(NotFoundError, "payment not found"):
        handlers.remove_payment(invoice.id, paid.document.payments[0].id)
    with pytest.raises(ValidationError) as amount:
        handlers.add_payment(invoice.id, PaymentInput(paid_on=TODAY, amount="viel"))
    assert amount.value.field == "amount"


def test_get_and_search(handlers: DocumentHandlers, store: Store) -> None:
    mueller = factories.customer(
        id=UUID(int=3), company_name="Müller AG", kind=CustomerKind.COMPANY
    )
    store.customers[mueller.id] = mueller
    first = handlers.create(DocumentType.INVOICE, draft_input(subject="Webseite")).document
    second = handlers.create(DocumentType.INVOICE, draft_input(customer_id=mueller.id)).document
    handlers.create(DocumentType.QUOTE, draft_input())
    assert handlers.get(first.id).document == first
    with raises_exactly(NotFoundError, "document not found"):
        handlers.get(new_id())
    invoices = handlers.search(DocumentQuery(today=TODAY, types=frozenset({DocumentType.INVOICE})))
    assert invoices.total == 2
    found = handlers.search(
        DocumentQuery(today=TODAY, types=frozenset({DocumentType.INVOICE}), search="mueller"),
    )
    assert [item.id for item in found.items] == [second.id]
    paged = handlers.search(
        DocumentQuery(
            today=TODAY,
            types=frozenset(DocumentType),
            statuses=frozenset({DisplayStatus.DRAFT}),
            customer_id=CUSTOMER,
            page=PageRequest(limit=1),
        ),
    )
    assert paged.total == 2
    assert len(paged.items) == 1


def _issued(handlers: DocumentHandlers, **overrides: object) -> UUID:
    draft = handlers.create(DocumentType.INVOICE, draft_input(**overrides)).document
    return handlers.issue(draft.id).document.id


def test_facets_sum_count_and_list_the_years(handlers: DocumentHandlers) -> None:
    last_year = _issued(handlers, issue_date=date(2025, 11, 20))
    paid = _issued(handlers)
    handlers.mark_paid(paid, TODAY)
    partly = _issued(handlers)
    handlers.add_payment(partly, PaymentInput(paid_on=TODAY, amount="1000"))
    cancelled = _issued(handlers)
    handlers.cancel(cancelled)
    handlers.create(DocumentType.INVOICE, draft_input())
    handlers.create(DocumentType.QUOTE, draft_input(issue_date=date(2024, 5, 1)))
    invoices = frozenset({DocumentType.INVOICE, DocumentType.CANCELLATION})
    total = Money(Decimal("1659.50"), Currency.CHF)

    facets = handlers.facets(DocumentQuery(today=TODAY, types=invoices))
    assert facets.years == [2026, 2025]
    assert facets.status_counts == {
        DisplayStatus.OVERDUE: 1,
        DisplayStatus.PAID: 1,
        DisplayStatus.PARTIALLY_PAID: 1,
        DisplayStatus.CANCELLED: 1,
        DisplayStatus.DRAFT: 1,
    }
    [chf] = facets.totals
    # Drafts, the cancelled invoice and its cancellation are left out.
    assert (chf.currency, chf.count) == (Currency.CHF, 3)
    assert chf.total == total * 3
    assert chf.open == total + total - Money(Decimal(1000), Currency.CHF)

    this_year = handlers.facets(
        DocumentQuery(
            today=TODAY,
            types=invoices,
            year=2026,
            statuses=frozenset({DisplayStatus.PAID}),
        ),
    )
    # The status filter narrows the totals but not the counts per status.
    assert this_year.status_counts[DisplayStatus.PAID] == 1
    assert DisplayStatus.OVERDUE not in this_year.status_counts
    assert [(item.count, item.open) for item in this_year.totals] == [(1, Money.zero(Currency.CHF))]
    found = handlers.search(DocumentQuery(today=TODAY, types=invoices, year=2025))
    assert [item.id for item in found.items] == [last_year]


def test_mark_several_paid_and_undo(
    handlers: DocumentHandlers, store: Store, units: list[InMemoryUnitOfWork]
) -> None:
    first, second = _issued(handlers), _issued(handlers)
    recorded = handlers.mark_paid_many([second, first, second], date(2026, 3, 5))
    assert [item.document_id for item in recorded] == sorted([first, second])
    assert all(isinstance(item.payment_id, UUID) for item in recorded)
    assert recorded[0].payment_id != recorded[1].payment_id
    assert units[-1].documents.locked == sorted([first, second])
    for item in recorded:
        document = store.documents[item.document_id].document
        assert document.status is DocumentStatus.PAID
        assert [payment.id for payment in document.payments] == [item.payment_id]
        assert document.payments[0].paid_on == date(2026, 3, 5)

    handlers.remove_payments(recorded)
    assert units[-1].documents.locked == sorted([first, second])
    for document_id in (first, second):
        assert store.documents[document_id].document.status is DocumentStatus.ISSUED
    with raises_exactly(NotFoundError, "payment not found"):
        handlers.remove_payments(recorded[:1])


def test_mark_several_paid_is_all_or_nothing(handlers: DocumentHandlers, store: Store) -> None:
    issued = _issued(handlers)
    draft = handlers.create(DocumentType.INVOICE, draft_input()).document.id
    with raises_exactly(InvalidStateError, f"{draft}: a draft invoice cannot be paid") as error:
        handlers.mark_paid_many([issued, draft], TODAY)
    assert (error.value.code, error.value.details) == (
        "cannot_mark_paid",
        {"document": str(draft)},
    )
    assert store.documents[issued].document.status is DocumentStatus.ISSUED
    with raises_exactly(ValidationError, "the payment date is in the future"):
        handlers.mark_paid_many([issued], TODAY + timedelta(days=1))
    paid = handlers.mark_paid_many([issued])
    assert store.documents[issued].document.payments[0].paid_on == TODAY
    with raises_exactly(NotFoundError, "document not found"):
        handlers.remove_payments(
            [*paid, RecordedPayment(document_id=new_id(), payment_id=new_id())]
        )
    assert store.documents[issued].document.status is DocumentStatus.PAID


def test_build_index(handlers: DocumentHandlers) -> None:
    view = handlers.create(DocumentType.INVOICE, draft_input(subject="Webseite", reference="PO-7"))
    index = build_index(view.document, view.totals, None)
    assert index.customer_name == ""
    assert index.search_text == "Webseite PO-7 Beratung Kaffee"
    assert index.net == view.totals.net
    assert index.open_amount == view.totals.total


def test_changes_lock_the_document(
    handlers: DocumentHandlers, units: list[InMemoryUnitOfWork]
) -> None:
    def locked_by(action: Callable[[], object]) -> list[UUID]:
        action()
        return units[-1].documents.locked

    invoice = handlers.create(DocumentType.INVOICE, draft_input()).document.id
    assert locked_by(lambda: handlers.get(invoice)) == []
    assert locked_by(lambda: handlers.update(invoice, draft_input())) == [invoice]
    assert locked_by(lambda: handlers.issue(invoice)) == [invoice]
    assert locked_by(lambda: handlers.duplicate(invoice)) == []
    assert locked_by(lambda: handlers.mark_paid(invoice, TODAY)) == [invoice]
    assert locked_by(lambda: handlers.cancel(invoice)) == [invoice]
    quote = handlers.create(DocumentType.QUOTE, draft_input()).document.id
    handlers.issue(quote)
    assert locked_by(lambda: handlers.accept(quote)) == [quote]
    assert locked_by(lambda: handlers.convert_to_invoice(quote)) == [quote]
    draft = handlers.create(DocumentType.INVOICE, draft_input()).document.id
    assert locked_by(lambda: handlers.delete(draft)) == [draft]


def test_preview_calculates_without_saving(
    handlers: DocumentHandlers, store: Store, units: list[InMemoryUnitOfWork]
) -> None:
    preview = handlers.preview(DocumentType.INVOICE, draft_input())
    view = preview.view
    assert view.totals.subtotal == Money(Decimal("1537.05"), Currency.CHF)
    assert preview.rates == {
        TaxCategory.STANDARD: Decimal("8.1"),
        TaxCategory.REDUCED: Decimal("2.6"),
        TaxCategory.SPECIAL: Decimal("3.8"),
        TaxCategory.ZERO: Decimal(0),
        TaxCategory.EXEMPT: Decimal(0),
    }
    export = handlers.preview(
        DocumentType.INVOICE,
        draft_input(treatment_override=TaxTreatment.EXPORT, issue_date=date(2023, 6, 1)),
    )
    assert set(export.rates.values()) == {Decimal(0)}
    # Germany has no special rate: the category is not offered.
    germany = factories.address(country=CountryCode("DE"))
    store.company = factories.company(address=germany)
    local = factories.customer(id=UUID(int=3), address=germany)
    store.customers[local.id] = local
    german = handlers.preview(DocumentType.INVOICE, draft_input(customer_id=local.id))
    assert german.rates[TaxCategory.STANDARD] == Decimal(19)
    assert TaxCategory.SPECIAL not in german.rates
    assert view.document.content.treatment is TaxTreatment.DOMESTIC
    assert view.display_status is DisplayStatus.DRAFT
    assert store.documents == {}
    assert [unit.commits for unit in units] == [0, 0, 0]
    with raises_exactly(ValidationError, "cancellations are created by cancelling an invoice"):
        handlers.preview(DocumentType.CANCELLATION, draft_input())


def test_converted_invoices_get_the_invoice_texts(handlers: DocumentHandlers, store: Store) -> None:
    def template(kind: TextKind, document_type: DocumentType, text: str, position: int = 0) -> None:
        created = TextTemplate(
            id=new_id(),
            kind=kind,
            document_type=document_type,
            language=Language.DE,
            name=text,
            text=text,
            is_default=True,
            position=position,
        )
        store.text_templates[created.id] = created

    template(TextKind.INTRO, DocumentType.QUOTE, "Gerne bieten wir an:")
    template(TextKind.CLOSING, DocumentType.QUOTE, "Gültig bis {faellig}.")
    template(TextKind.INTRO, DocumentType.INVOICE, "Danke für den Auftrag.")
    template(TextKind.PAYMENT, DocumentType.INVOICE, "Zahlbar bis {faellig}.")
    template(TextKind.PAYMENT, DocumentType.INVOICE, "Nummer {nummer} angeben.", 1)
    # An English default must not count for a German document.
    store.text_templates[new_id()] = TextTemplate(
        id=new_id(),
        kind=TextKind.CLOSING,
        document_type=DocumentType.INVOICE,
        language=Language.EN,
        name="Thanks",
        text="Thanks",
        is_default=True,
    )
    quote = handlers.create(
        DocumentType.QUOTE,
        draft_input(
            intro_text="Gerne bieten wir an:",
            closing_text="Gültig bis {faellig}.",
            payment_text="",
        ),
    ).document
    handlers.issue(quote.id)
    invoice = handlers.convert_to_invoice(quote.id).document
    assert invoice.content.intro_text == "Danke für den Auftrag."
    assert invoice.content.payment_text == "Zahlbar bis {faellig}.\nNummer {nummer} angeben."
    assert invoice.content.closing_text == ""

    # Texts the user wrote stay as they are.
    own = handlers.create(DocumentType.QUOTE, draft_input(intro_text="Hallo Anna")).document
    handlers.issue(own.id)
    kept = handlers.convert_to_invoice(own.id).document
    assert kept.content.intro_text == "Hallo Anna"
