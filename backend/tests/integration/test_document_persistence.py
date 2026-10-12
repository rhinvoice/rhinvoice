"""Documents in PostgreSQL: round trip, immutability triggers, search and figures."""

import hashlib
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from rhinvoice.application.common import AddressInput, PageRequest, SortDirection
from rhinvoice.application.company.handlers import CompanyHandlers, SaveBankAccount, SaveCompany
from rhinvoice.application.customer.handlers import CustomerHandlers, SaveCustomer
from rhinvoice.application.document.handlers import (
    DocumentHandlers,
    DraftInput,
    LineInput,
    PaymentInput,
)
from rhinvoice.application.document.ports import DocumentQuery, DocumentSort
from rhinvoice.application.text.handlers import SaveTextTemplate, TextHandlers
from rhinvoice.domain.customer.customer import CustomerKind
from rhinvoice.domain.document.document import (
    DisplayStatus,
    DocumentStatus,
    DocumentType,
    EventKind,
)
from rhinvoice.domain.document.lines import DiscountKind, LineKind, PriceMode
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency, Money
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply
from rhinvoice.domain.tax.treatment import TaxTreatment
from rhinvoice.domain.text.template import TextKind
from rhinvoice.infrastructure.db.uow import SqlUnitOfWork
from tests.unit.domain.factories import CH_IBAN, CH_QR_IBAN

NOW = datetime(2026, 3, 9, 9, 0, tzinfo=UTC)
TODAY = NOW.date()
ZURICH = AddressInput(
    street="Bahnhofstrasse", house_number="1", postal_code="8001", city="Zürich", country="CH"
)
HOURS = LineInput(
    kind=LineKind.ITEM,
    description="Beratung Müller-Projekt",
    quantity="10",
    unit="HUR",
    unit_price="150",
)
FOOD = LineInput(
    kind=LineKind.ITEM,
    description="Verpflegung",
    details="Kaffee und Gipfeli",
    quantity="3",
    unit="C62",
    unit_price="12.35",
    tax_category=TaxCategory.REDUCED,
)


def factory(engine: Engine) -> Callable[[], SqlUnitOfWork]:
    return lambda: SqlUnitOfWork(engine)


@pytest.fixture
def setup(engine: Engine) -> tuple[DocumentHandlers, UUID, FixedClock]:
    CompanyHandlers(uow=factory(engine)).save(
        SaveCompany(
            name="Muster GmbH",
            address=ZURICH,
            default_currency=Currency.CHF,
            vat_number="CHE-123.456.788",
            cash_rounding=True,
        ),
    )
    CompanyHandlers(uow=factory(engine)).create_bank_account(
        SaveBankAccount(
            currency=Currency.CHF,
            bank_name="Bank",
            holder="Muster",
            iban=CH_IBAN,
            qr_iban=CH_QR_IBAN,
        ),
    )
    clock = FixedClock(NOW)
    customer = CustomerHandlers(uow=factory(engine), clock=clock).create(
        SaveCustomer(kind=CustomerKind.COMPANY, company_name="Müller AG", address=ZURICH),
    )
    return DocumentHandlers(uow=factory(engine), clock=clock), customer.id, clock


def draft(customer: UUID, **overrides: object) -> DraftInput:
    values: dict[str, object] = {"customer_id": customer, "lines": (HOURS, FOOD)}
    values.update(overrides)
    return DraftInput(**values)  # type: ignore[arg-type]  # test builder


def test_round_trip_of_drafts_and_issued_documents(
    setup: tuple[DocumentHandlers, UUID, FixedClock],
) -> None:
    handlers, customer, _ = setup
    created = handlers.create(
        DocumentType.INVOICE,
        draft(
            customer,
            subject="Website",
            reference="PO 7",
            intro_text="Guten Tag\nwie besprochen",
            closing_text="Danke",
            discount_kind=DiscountKind.AMOUNT,
            discount_value="10",
            price_mode=PriceMode.GROSS,
            service_from=date(2026, 2, 1),
            service_to=date(2026, 2, 28),
            treatment_override=TaxTreatment.DOMESTIC,
            override_reason="geprüft",
        ),
    ).document
    assert handlers.get(created.id).document == created

    issued = handlers.issue(created.id).document
    loaded = handlers.get(created.id)
    assert loaded.document == issued
    assert loaded.document.snapshot == issued.snapshot
    assert loaded.document.issued_totals == issued.issued_totals
    assert [line.tax_rate for line in loaded.document.content.lines] == [
        Decimal("8.1"),
        Decimal("2.6"),
    ]

    paid = handlers.add_payment(
        created.id, PaymentInput(paid_on=TODAY, amount="100", note="Anzahlung")
    )
    assert handlers.get(created.id).document == paid.document
    without = handlers.remove_payment(created.id, paid.document.payments[0].id)
    assert handlers.get(created.id).document == without.document


def test_goods_are_persisted_with_their_treatment(
    engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    handlers, _, clock = setup
    vienna = AddressInput(
        street="Ring", house_number="1", postal_code="1010", city="Wien", country="AT"
    )
    austrian = CustomerHandlers(uow=factory(engine), clock=clock).create(
        SaveCustomer(
            kind=CustomerKind.COMPANY,
            company_name="Kunde Wien GmbH",
            address=vienna,
            vat_number="ATU12345678",
        ),
    )
    printer = replace(HOURS, description="Drucker", unit="C62", supply=Supply.GOODS)
    created = handlers.create(
        DocumentType.INVOICE, draft(austrian.id, lines=(HOURS, printer))
    ).document
    assert handlers.get(created.id).document == created
    assert [line.supply for line in created.content.lines] == [Supply.SERVICE, Supply.GOODS]
    issued = handlers.issue(created.id)
    assert issued.document.content.goods_treatment is TaxTreatment.GOODS_EXPORT
    loaded = handlers.get(created.id)
    assert loaded.document == issued.document
    assert loaded.notices == issued.notices
    assert loaded.document.issued_snapshot.goods_notice == (
        "Steuerbefreite Ausfuhrlieferung (Art. 23 Abs. 2 Ziff. 1 MWSTG)."
    )
    for statement in (
        "UPDATE documents SET goods_treatment = 'domestic' WHERE id = :id",
        "UPDATE document_lines SET supply = 'service' WHERE document_id = :id",
    ):
        with engine.begin() as connection, pytest.raises(IntegrityError, match="immutable"):
            connection.execute(text(statement), {"id": created.id})


def test_cancellation_and_conversion_are_persisted(
    setup: tuple[DocumentHandlers, UUID, FixedClock],
) -> None:
    handlers, customer, _ = setup
    quote = handlers.issue(
        handlers.create(DocumentType.QUOTE, draft(customer)).document.id
    ).document
    invoice = handlers.convert_to_invoice(quote.id).document
    assert handlers.get(quote.id).document.status is DocumentStatus.ACCEPTED
    issued = handlers.issue(invoice.id).document
    cancelled = handlers.cancel(issued.id).document
    assert handlers.get(issued.id).document == cancelled
    assert cancelled.cancelled_by_id is not None
    cancellation = handlers.get(cancelled.cancelled_by_id).document
    assert cancellation.number == "S20260001"
    assert cancellation.source_id == issued.id
    assert handlers.get(quote.id).document.converted_to_id == invoice.id
    # A cancellation is due on its issue date but never listed as overdue.
    later = TODAY + timedelta(days=60)
    cancellations = frozenset({DocumentType.CANCELLATION})

    def found(status: DisplayStatus) -> list[DisplayStatus]:
        query = DocumentQuery(today=later, types=cancellations, statuses=frozenset({status}))
        return [summary.display_status for summary in handlers.search(query).items]

    assert found(DisplayStatus.OVERDUE) == []
    assert found(DisplayStatus.ISSUED) == [DisplayStatus.ISSUED]


def test_issued_documents_are_protected_by_triggers(
    engine: Engine,
    setup: tuple[DocumentHandlers, UUID, FixedClock],
) -> None:
    handlers, customer, _ = setup
    document = handlers.issue(
        handlers.create(DocumentType.INVOICE, draft(customer)).document.id
    ).document
    statements = [
        "UPDATE documents SET subject = 'manipuliert' WHERE id = :id",
        "UPDATE documents SET number = 'X' WHERE id = :id",
        "UPDATE documents SET status = 'draft', number = NULL WHERE id = :id",
        "UPDATE document_lines SET unit_price = 1 WHERE document_id = :id",
        (
            "INSERT INTO document_lines (id, document_id, position, kind, quantity, unit_price,"
            " discount_percent, tax_category)"
            " VALUES (gen_random_uuid(), :id, 99, 'item', 1, 1, 0, 'standard')"
        ),
        "DELETE FROM document_lines WHERE document_id = :id",
        "DELETE FROM documents WHERE id = :id",
        "UPDATE documents SET treatment_overridden = NOT treatment_overridden WHERE id = :id",
        "UPDATE documents SET created_at = created_at - interval '1 day' WHERE id = :id",
        "UPDATE documents SET source_id = id WHERE id = :id",
        "UPDATE document_events SET detail = 'x' WHERE document_id = :id",
        "DELETE FROM document_events WHERE document_id = :id",
    ]
    for statement in statements:
        with (
            engine.begin() as connection,
            pytest.raises(IntegrityError, match=r"immutable|cannot be deleted|append-only"),
        ):
            connection.execute(text(statement), {"id": document.id})
    paid = handlers.add_payment(document.id, PaymentInput(paid_on=TODAY, amount="10")).document
    with (
        engine.begin() as connection,
        pytest.raises(IntegrityError, match="payments cannot be changed, only removed"),
    ):
        connection.execute(
            text("UPDATE document_payments SET amount = 1 WHERE document_id = :id"),
            {"id": document.id},
        )
    handlers.remove_payment(document.id, paid.payments[0].id)  # removing stays possible
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE documents SET pdf_sha256 = :hash WHERE id = :id"),
            {"id": document.id, "hash": "a" * 64},
        )
    with engine.begin() as connection, pytest.raises(IntegrityError, match="immutable"):
        connection.execute(
            text("UPDATE documents SET pdf_sha256 = :hash WHERE id = :id"),
            {"id": document.id, "hash": "b" * 64},
        )
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE documents SET status = 'paid' WHERE id = :id"), {"id": document.id}
        )


def test_deleting_a_converted_draft_frees_the_quote(
    setup: tuple[DocumentHandlers, UUID, FixedClock],
) -> None:
    handlers, customer, _ = setup
    quote = handlers.issue(handlers.create(DocumentType.QUOTE, draft(customer)).document.id)
    invoice = handlers.convert_to_invoice(quote.document.id).document
    handlers.delete(invoice.id)
    freed = handlers.get(quote.document.id).document
    assert freed.converted_to_id is None
    assert freed.events[-1].kind is EventKind.CONVERTED  # the history stays
    assert handlers.convert_to_invoice(quote.document.id).document.source_id == quote.document.id


def test_latest_issue_date(
    engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    handlers, customer, _ = setup
    handlers.create(DocumentType.INVOICE, draft(customer, issue_date=TODAY))
    with SqlUnitOfWork(engine) as uow:
        assert uow.documents.latest_issue_date(DocumentType.INVOICE) is None
    for day in (date(2026, 1, 3), date(2026, 1, 7)):
        handlers.issue(
            handlers.create(DocumentType.INVOICE, draft(customer, issue_date=day)).document.id
        )
    with SqlUnitOfWork(engine) as uow:
        assert uow.documents.latest_issue_date(DocumentType.INVOICE) == date(2026, 1, 7)
        assert uow.documents.latest_issue_date(DocumentType.QUOTE) is None


def test_drafts_can_be_changed_and_deleted(
    engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    handlers, customer, _ = setup
    document = handlers.create(DocumentType.INVOICE, draft(customer)).document
    updated = handlers.update(document.id, draft(customer, lines=(FOOD,), subject="Neu")).document
    assert handlers.get(document.id).document == updated
    handlers.delete(document.id)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM document_lines")).scalar_one() == 0


def test_search_filters_and_sorting(setup: tuple[DocumentHandlers, UUID, FixedClock]) -> None:
    handlers, customer, clock = setup
    first = handlers.issue(
        handlers.create(DocumentType.INVOICE, draft(customer, subject="Website")).document.id
    ).document
    second = handlers.issue(
        handlers.create(
            DocumentType.INVOICE, draft(customer, subject="Hosting", lines=(FOOD,))
        ).document.id,
    ).document
    handlers.create(DocumentType.INVOICE, draft(customer, subject="Entwurf"))
    quote = handlers.issue(
        handlers.create(DocumentType.QUOTE, draft(customer)).document.id
    ).document
    later = TODAY + timedelta(days=40)
    invoices = frozenset({DocumentType.INVOICE})

    def search(**kwargs: object) -> list[UUID]:
        query = DocumentQuery(**{"today": TODAY, "types": invoices, **kwargs})  # type: ignore[arg-type]
        return [item.id for item in handlers.search(query).items]

    assert set(search()) >= {first.id, second.id}
    assert search(search="websi") == [first.id]
    assert search(search="Mueller Website") == [first.id]
    assert search(search="hosting") == [second.id]
    assert len(search(search="gipfeli")) == 3
    assert search(search="R20260002") == [second.id]
    assert search(search="!!!") == search()
    assert search(
        sort=DocumentSort.NUMBER,
        direction=SortDirection.ASC,
        statuses=frozenset({DisplayStatus.ISSUED}),
    ) == [
        first.id,
        second.id,
    ]
    assert (
        search(
            sort=DocumentSort.TOTAL,
            direction=SortDirection.ASC,
            statuses=frozenset({DisplayStatus.ISSUED}),
        )[0]
        == second.id
    )
    overdue = handlers.search(
        DocumentQuery(today=later, types=invoices, statuses=frozenset({DisplayStatus.OVERDUE})),
    )
    assert {item.id for item in overdue.items} == {first.id, second.id}
    assert {item.display_status for item in overdue.items} == {DisplayStatus.OVERDUE}
    not_overdue = handlers.search(
        DocumentQuery(today=later, types=invoices, statuses=frozenset({DisplayStatus.ISSUED}))
    )
    assert not_overdue.items == []
    expired = handlers.search(
        DocumentQuery(
            today=later,
            types=frozenset({DocumentType.QUOTE}),
            statuses=frozenset({DisplayStatus.EXPIRED}),
        ),
    )
    assert [item.id for item in expired.items] == [quote.id]
    drafts = handlers.search(
        DocumentQuery(today=TODAY, types=invoices, statuses=frozenset({DisplayStatus.DRAFT}))
    )
    assert drafts.total == 1
    assert drafts.items[0].number is None
    by_customer = handlers.search(
        DocumentQuery(
            today=TODAY,
            types=frozenset(DocumentType),
            customer_id=customer,
            page=PageRequest(limit=2),
        ),
    )
    assert by_customer.total == 4
    assert len(by_customer.items) == 2
    for sort in DocumentSort:
        assert handlers.search(DocumentQuery(today=TODAY, types=invoices, sort=sort)).total == 3
    assert clock.now() == NOW


def test_dashboard_figures(
    engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    handlers, customer, _ = setup
    first = handlers.issue(
        handlers.create(DocumentType.INVOICE, draft(customer)).document.id
    ).document
    second = handlers.issue(
        handlers.create(DocumentType.INVOICE, draft(customer, lines=(FOOD,))).document.id
    ).document
    handlers.add_payment(first.id, PaymentInput(paid_on=TODAY, amount="1000"))
    third = handlers.issue(
        handlers.create(DocumentType.INVOICE, draft(customer, lines=(FOOD,))).document.id
    ).document
    handlers.cancel(third.id)
    with SqlUnitOfWork(engine) as uow:
        figures = uow.documents.figures(TODAY + timedelta(days=31))
        revenue = uow.documents.revenue_by_month(date(2026, 1, 1))
        events = uow.documents.recent_events(5, TODAY)
    assert len(figures) == 1
    chf = figures[0]
    assert chf.currency is Currency.CHF
    assert chf.open == Money(Decimal("659.50"), Currency.CHF) + Money(
        Decimal("38.00"), Currency.CHF
    )
    assert chf.overdue == chf.open
    assert chf.open_count == 2
    assert chf.overdue_count == 2
    assert chf.paid == Money(Decimal(1000), Currency.CHF)
    assert len(revenue) == 1
    assert revenue[0].month == date(2026, 3, 1)
    assert revenue[0].net == Money(Decimal("1537.05") + Decimal("37.05"), Currency.CHF)
    assert len(events) == 5
    assert events[0][1] == "cancelled"
    assert second.number == "R20260002"


def test_revenue_by_customer_and_days_to_pay(
    engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    handlers, customer, _ = setup

    def issued(**overrides: object) -> UUID:
        created = handlers.create(DocumentType.INVOICE, draft(customer, **overrides)).document
        return handlers.issue(created.id).document.id

    old = issued(issue_date=date(2025, 11, 20))
    handlers.mark_paid(old, date(2025, 12, 1))
    paid = issued(issue_date=TODAY - timedelta(days=4))
    handlers.add_payment(paid, PaymentInput(paid_on=TODAY - timedelta(days=3), amount="500"))
    handlers.mark_paid(paid, TODAY)
    # Renamed before the latest documents: the overview names the customer as now.
    with SqlUnitOfWork(engine) as uow:
        current = uow.customers.get(customer)
        assert current is not None
        uow.customers.update(replace(current, company_name="Müller & Söhne AG"))
        uow.commit()
    issued(lines=(FOOD,))
    handlers.cancel(issued(lines=(FOOD,)))
    with SqlUnitOfWork(engine) as uow:
        this_year = uow.documents.revenue_by_customer(date(2026, 1, 1))
        everything = uow.documents.revenue_by_customer(date(2025, 1, 1))
        days = uow.documents.days_to_pay(date(2025, 1, 1))
        recent_days = uow.documents.days_to_pay(date(2026, 1, 1))
        year_to_date = uow.documents.revenue_between(date(2026, 1, 1), TODAY)
        last_year = uow.documents.revenue_between(date(2025, 1, 1), date(2025, 11, 19))
    # The cancelled invoice and its cancellation offset each other.
    [entry] = this_year
    assert (entry.customer_id, entry.currency) == (customer, Currency.CHF)
    assert entry.net == Money(Decimal("1537.05") + Decimal("37.05"), Currency.CHF)
    assert entry.customer_name == "Müller & Söhne AG"
    assert everything[0].net == entry.net + Money(Decimal("1537.05"), Currency.CHF)
    assert year_to_date == {Currency.CHF: entry.net}
    assert last_year == {}
    # Paid after 11 days last year, after 4 days (the last payment) this year.
    assert days == [(Currency.CHF, 11), (Currency.CHF, 4)]
    assert recent_days == [(Currency.CHF, 4)]


def test_facets_and_year_filter(setup: tuple[DocumentHandlers, UUID, FixedClock]) -> None:
    handlers, customer, clock = setup

    def issued(**overrides: object) -> UUID:
        created = handlers.create(DocumentType.INVOICE, draft(customer, **overrides)).document
        return handlers.issue(created.id).document.id

    last_year = issued(issue_date=date(2025, 11, 20))
    paid = issued()
    handlers.mark_paid(paid, TODAY)
    partly = issued()
    handlers.add_payment(partly, PaymentInput(paid_on=TODAY, amount="1000"))
    handlers.cancel(issued())
    handlers.create(DocumentType.INVOICE, draft(customer))
    handlers.create(DocumentType.QUOTE, draft(customer, issue_date=date(2024, 5, 1)))
    # 00:30 in Zurich on 1 January 2027 is still 2026 in UTC.
    clock.current = datetime(2026, 12, 31, 23, 30, tzinfo=UTC)
    new_year_draft = handlers.create(DocumentType.INVOICE, draft(customer)).document.id
    clock.current = NOW
    invoices = frozenset({DocumentType.INVOICE, DocumentType.CANCELLATION})
    total = Money(Decimal("1659.50"), Currency.CHF)

    facets = handlers.facets(DocumentQuery(today=TODAY, types=invoices))
    assert facets.years == [2027, 2026, 2025]
    assert facets.status_counts == {
        DisplayStatus.OVERDUE: 1,
        DisplayStatus.PAID: 1,
        DisplayStatus.PARTIALLY_PAID: 1,
        DisplayStatus.CANCELLED: 1,
        DisplayStatus.DRAFT: 2,
    }
    [chf] = facets.totals
    assert (chf.currency, chf.count) == (Currency.CHF, 3)
    assert chf.total == total * 3
    assert chf.open == total + total - Money(Decimal(1000), Currency.CHF)

    paid_this_year = handlers.facets(
        DocumentQuery(
            today=TODAY,
            types=invoices,
            year=2026,
            statuses=frozenset({DisplayStatus.PAID}),
        ),
    )
    assert paid_this_year.status_counts[DisplayStatus.PAID] == 1
    assert DisplayStatus.OVERDUE not in paid_this_year.status_counts
    assert [(item.count, item.open) for item in paid_this_year.totals] == [
        (1, Money.zero(Currency.CHF))
    ]
    quotes = handlers.facets(DocumentQuery(today=TODAY, types=frozenset({DocumentType.QUOTE})))
    assert quotes.years == [2024]
    assert quotes.totals == []

    def year(value: int) -> list[UUID]:
        query = DocumentQuery(today=TODAY, types=invoices, year=value)
        return [item.id for item in handlers.search(query).items]

    assert year(2025) == [last_year]
    assert year(2027) == [new_year_draft]
    assert year(2024) == []
    # In New York the draft was created on 31 December 2026.
    new_york = DocumentQuery(
        today=TODAY, types=invoices, year=2027, zone=ZoneInfo("America/New_York")
    )
    assert handlers.search(new_york).items == []


def test_unknown_documents_and_empty_drafts(
    engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    handlers, customer, _ = setup
    empty = handlers.create(DocumentType.INVOICE, draft(customer, lines=())).document
    assert handlers.get(empty.id).document.content.lines == ()
    with SqlUnitOfWork(engine) as uow:
        assert uow.documents.get(UUID(int=0)) is None
        assert not uow.documents.number_exists(DocumentType.INVOICE, "R1")


def test_texts_and_notices_are_persisted(
    engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    handlers, customer, _ = setup
    texts = TextHandlers(uow=factory(engine))
    first = texts.create_template(
        SaveTextTemplate(
            kind=TextKind.CLOSING,
            document_type=DocumentType.QUOTE,
            language=Language.DE,
            name="Gültigkeit",
            text="Gültig bis {faellig}.",
        ),
    )
    texts.create_template(
        SaveTextTemplate(
            kind=TextKind.INTRO,
            document_type=DocumentType.QUOTE,
            language=Language.DE,
            name="Anfrage",
            text="Danke für Ihre Anfrage.",
        ),
    )
    created = texts.create_template(
        SaveTextTemplate(
            kind=TextKind.CLOSING,
            document_type=DocumentType.QUOTE,
            language=Language.DE,
            name="Gruss",
            text="Freundliche Grüsse",
            is_default=True,
        ),
    )
    assert created.position == 1
    with SqlUnitOfWork(engine) as uow:
        assert uow.text_templates.get(created.id) == created
        assert uow.text_templates.get(UUID(int=0)) is None
    texts.update_template(
        created.id,
        SaveTextTemplate(
            kind=TextKind.CLOSING,
            document_type=DocumentType.QUOTE,
            language=Language.DE,
            name="Grüsse",
            text="Beste Grüsse",
        ),
    )
    moved = texts.move_template(created.id, up=True)
    quote_closings = [
        (t.name, t.position)
        for t in moved
        if (t.document_type, t.language, t.kind)
        == (DocumentType.QUOTE, Language.DE, TextKind.CLOSING)
    ]
    assert quote_closings == [("Grüsse", 0), ("Gültigkeit", 1)]
    assert [t.kind for t in moved] == [TextKind.INTRO, TextKind.CLOSING, TextKind.CLOSING]
    texts.delete_template(created.id)
    assert [t.id for t in texts.list_templates() if t.kind is TextKind.CLOSING] == [first.id]

    reverse = TaxTreatment.REVERSE_CHARGE
    texts.save_notice(reverse, Language.DE, "Erster Wortlaut.")
    texts.save_notice(reverse, Language.DE, "Zweiter Wortlaut.")
    with SqlUnitOfWork(engine) as uow:
        assert uow.legal_notices.all() == {(reverse, Language.DE): "Zweiter Wortlaut."}
        assert uow.legal_notices.get(reverse, Language.EN) is None
    created_invoice = handlers.create(
        DocumentType.INVOICE,
        draft(
            customer,
            treatment_override=reverse,
            override_reason="EU",
            payment_text="Zahlbar sofort.",
        ),
    )
    assert created_invoice.notice == "Zweiter Wortlaut."
    loaded = handlers.get(created_invoice.document.id)
    assert loaded.document.content.payment_text == "Zahlbar sofort."
    texts.save_notice(reverse, Language.DE, "")
    with SqlUnitOfWork(engine) as uow:
        assert uow.legal_notices.all() == {}


def test_archived_pdfs_are_protected(
    engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    handlers, customer, _ = setup
    issued = handlers.issue(handlers.create(DocumentType.INVOICE, draft(customer)).document.id)
    document = issued.document
    content = b"%PDF-1.7 archived"
    archived = document.archive_pdf(hashlib.sha256(content).hexdigest())
    with SqlUnitOfWork(engine) as uow:
        assert uow.documents.get_pdf(document.id) is None
        assert uow.documents.get_e_invoice(document.id) is None
        uow.documents.archive_pdf(archived, content, b"<invoice/>")
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        assert uow.documents.get_pdf(document.id) == content
        assert uow.documents.get_e_invoice(document.id) == b"<invoice/>"
        loaded = uow.documents.get(document.id)
        assert loaded is not None
        assert loaded.pdf_sha256 == archived.pdf_sha256

    def rejected(statement: str, message: str) -> None:
        with engine.begin() as connection, pytest.raises(IntegrityError, match=message):
            connection.execute(text(statement), {"id": document.id})

    rejected(
        "UPDATE document_pdfs SET content = 'x' WHERE document_id = :id",
        "archived PDFs cannot be changed or deleted",
    )
    rejected(
        "UPDATE document_pdfs SET e_invoice = NULL WHERE document_id = :id",
        "archived PDFs cannot be changed or deleted",
    )
    rejected(
        "DELETE FROM document_pdfs WHERE document_id = :id",
        "archived PDFs cannot be changed or deleted",
    )
    rejected("TRUNCATE document_pdfs CASCADE", "archived PDFs cannot be changed or deleted")
    rejected(
        "UPDATE documents SET pdf_sha256 = repeat('b', 64) WHERE id = :id",
        "issued documents are immutable",
    )
    other = handlers.issue(handlers.create(DocumentType.INVOICE, draft(customer)).document.id)
    with (
        engine.begin() as connection,
        pytest.raises(IntegrityError, match="the PDF does not match the hash of its document"),
    ):
        connection.execute(
            text("INSERT INTO document_pdfs (document_id, content) VALUES (:id, 'x')"),
            {"id": other.document.id},
        )


def test_documents_issued_by_an_older_version_can_be_paid_and_cancelled(
    engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    handlers, customer, _ = setup
    created = handlers.create(DocumentType.INVOICE, draft(customer)).document
    invoice = handlers.issue(created.id).document
    # Version 0.3.0 stored the snapshot without these keys; the trigger guards it.
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE documents DISABLE TRIGGER protect_document"))
        connection.execute(
            text(
                "UPDATE documents SET snapshot = snapshot - 'layout' - 'accounts' - 'notice'"
                " WHERE id = :id"
            ),
            {"id": invoice.id},
        )
        connection.execute(text("ALTER TABLE documents ENABLE TRIGGER protect_document"))
    handlers.mark_paid(invoice.id, TODAY)
    handlers.cancel(invoice.id)
    with SqlUnitOfWork(engine) as uow:
        stored = uow.documents.get(invoice.id)
    assert stored is not None
    assert stored.status is DocumentStatus.CANCELLED
    with engine.connect() as connection:
        snapshot = connection.execute(
            text("SELECT snapshot FROM documents WHERE id = :id"), {"id": invoice.id}
        ).scalar_one()
    assert "layout" not in snapshot
