from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from rhinvoice.application.document.dashboard import (
    RECENT_EVENTS,
    Aging,
    DashboardHandlers,
    DaysToPay,
    ExpectedWeek,
    QuoteFigures,
    YearToDate,
    aging,
    average_days,
    days_to_pay,
    expected_payments,
    first_per_currency,
    quote_figures,
    same_day_last_year,
    top_customers,
    week_start,
    year_to_date,
)
from rhinvoice.application.document.handlers import (
    DocumentHandlers,
    DraftInput,
    LineInput,
    PaymentInput,
)
from rhinvoice.application.document.ports import (
    CurrencyFigures,
    CustomerRevenue,
    DocumentSummary,
    MonthlyRevenue,
)
from rhinvoice.domain.document.document import DisplayStatus, DocumentStatus, DocumentType
from rhinvoice.domain.document.lines import LineKind
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Currency, Money
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories

CUSTOMER = UUID(int=1)
LINE = LineInput(
    kind=LineKind.ITEM, description="Beratung", quantity="1", unit="HUR", unit_price="100"
)


def chf(amount: str) -> Money:
    return Money(Decimal(amount), Currency.CHF)


@pytest.fixture
def documents(store: Store, clock: FixedClock) -> DocumentHandlers:
    store.company = factories.company(payment_terms_days=30)
    for currency in (Currency.CHF, Currency.EUR):
        account = factories.bank_account(currency=currency, is_default=True)
        store.bank_accounts[account.id] = account
    customer = factories.customer(id=CUSTOMER, payment_terms_days=None)
    store.customers[customer.id] = customer
    return DocumentHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)


@pytest.fixture
def dashboard(store: Store, clock: FixedClock) -> DashboardHandlers:
    return DashboardHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)


def issued(
    documents: DocumentHandlers,
    issue_date: date,
    *,
    document_type: DocumentType = DocumentType.INVOICE,
    currency: Currency | None = None,
) -> UUID:
    draft = DraftInput(
        customer_id=CUSTOMER, lines=(LINE,), issue_date=issue_date, currency=currency
    )
    document_id = documents.create(document_type, draft).document.id
    documents.issue(document_id)
    return document_id


def test_empty_dashboard(dashboard: DashboardHandlers) -> None:
    overview = dashboard.overview()
    assert overview.figures == []
    assert overview.revenue == []
    assert overview.recent == []
    assert (overview.aging, overview.expected, overview.overdue) == ([], [], [])
    assert (overview.quotes, overview.top_customers, overview.days_to_pay) == ([], [], [])
    assert (overview.year_to_date, overview.today) == ([], date(2026, 3, 9))


def test_the_company_currency_comes_first(store: Store, dashboard: DashboardHandlers) -> None:
    """An Austrian company sees euros first, even before its first invoice."""
    store.company = None
    assert dashboard.overview().currency is None
    store.company = factories.company(default_currency=Currency.EUR)
    assert dashboard.overview().currency is Currency.EUR


def test_overview_sums_invoices_per_currency(
    documents: DocumentHandlers, dashboard: DashboardHandlers
) -> None:
    # Issued in date order: a document may not be dated before the last one.
    issued(documents, date(2025, 3, 31))  # before the revenue window, still overdue
    overdue = issued(documents, date(2026, 1, 5))
    cancelled = issued(documents, date(2026, 2, 10))
    partly_paid = issued(documents, date(2026, 3, 2))
    documents.add_payment(partly_paid, PaymentInput(paid_on=date(2026, 3, 5), amount="8.10"))
    paid = issued(documents, date(2026, 3, 3), currency=Currency.EUR)
    documents.mark_paid(paid, date(2026, 3, 6))
    documents.cancel(cancelled)
    issued(documents, date(2026, 3, 4), document_type=DocumentType.QUOTE)
    documents.create(DocumentType.INVOICE, DraftInput(customer_id=CUSTOMER, lines=(LINE,)))

    overview = dashboard.overview()

    assert overview.figures == [
        CurrencyFigures(
            currency=Currency.CHF,
            open=chf("316.20"),
            overdue=chf("216.20"),
            paid=chf("8.10"),
            open_count=3,
            overdue_count=2,
        ),
        CurrencyFigures(
            currency=Currency.EUR,
            open=Money.zero(Currency.EUR),
            overdue=Money.zero(Currency.EUR),
            paid=Money(Decimal("108.10"), Currency.EUR),
            open_count=0,
            overdue_count=0,
        ),
    ]
    # Since January of last year: this year against last year.
    assert overview.revenue == [
        MonthlyRevenue(month=date(2025, 3, 1), currency=Currency.CHF, net=chf("100.00")),
        MonthlyRevenue(month=date(2026, 1, 1), currency=Currency.CHF, net=chf("100.00")),
        MonthlyRevenue(month=date(2026, 2, 1), currency=Currency.CHF, net=chf("100.00")),
        MonthlyRevenue(month=date(2026, 3, 1), currency=Currency.CHF, net=chf("0.00")),
        MonthlyRevenue(
            month=date(2026, 3, 1), currency=Currency.EUR, net=Money(Decimal(100), Currency.EUR)
        ),
    ]
    assert len(overview.recent) == RECENT_EVENTS
    assert overdue not in {summary.id for summary, _, _ in overview.recent}  # oldest dropped
    # Today is Monday 2026-03-09: 313 and 33 days late, one not due yet.
    assert overview.aging == [
        Aging(Currency.CHF, chf("100.00"), chf("0"), chf("108.10"), chf("108.10"))
    ]
    assert [summary.id for summary in overview.overdue][1:] == [overdue]
    assert len(overview.overdue) == 2
    expected = [(week.week_start, week.amount) for week in overview.expected]
    assert expected[0] == (date(2026, 3, 9), chf("216.20"))
    assert expected[3] == (date(2026, 3, 30), chf("100.00"))
    assert len(expected) == 6
    assert overview.quotes == [QuoteFigures(Currency.CHF, chf("108.10"), 1, 0, 0)]
    assert [(entry.currency, entry.net.amount) for entry in overview.top_customers] == [
        (Currency.CHF, Decimal("200.00")),
        (Currency.EUR, Decimal("100.00")),
    ]
    assert overview.top_customers[0].customer_name == "Beispiel AG"
    assert overview.days_to_pay == [DaysToPay(Currency.EUR, 3)]
    # 1 January to 9 March, against last year to 9 March (the 2025-03-31 invoice is later).
    assert overview.year_to_date == [
        YearToDate(Currency.CHF, chf("200.00"), chf("0")),
        YearToDate(Currency.EUR, Money(Decimal(100), Currency.EUR), Money.zero(Currency.EUR)),
    ]


def test_recent_events_are_newest_first(
    documents: DocumentHandlers, dashboard: DashboardHandlers, clock: FixedClock
) -> None:
    first = issued(documents, date(2026, 3, 1))
    clock.set(clock.now().replace(hour=10))
    second = issued(documents, date(2026, 3, 2))
    recent = dashboard.overview().recent
    assert [(summary.id, kind) for summary, kind, _ in recent] == [
        (second, "issued"),
        (second, "created"),
        (first, "issued"),
        (first, "created"),
    ]


def summary(
    due: date | None,
    amount: str = "10",
    currency: Currency = Currency.CHF,
    status: DisplayStatus = DisplayStatus.ISSUED,
) -> DocumentSummary:
    money = Money(Decimal(amount), currency)
    return DocumentSummary(
        id=new_id(),
        type=DocumentType.INVOICE,
        status=DocumentStatus.ISSUED,
        display_status=status,
        number="R1",
        customer_id=CUSTOMER,
        customer_name="Beispiel AG",
        subject="",
        issue_date=date(2026, 1, 1),
        due_date=due,
        currency=currency,
        total=money,
        open_amount=money,
        created_at=NOW,
    )


TODAY = date(2026, 3, 11)


def test_aging_buckets_by_days_late() -> None:
    invoices = [
        summary(TODAY, "1"),
        summary(None, "2"),
        summary(TODAY - timedelta(days=1), "4"),
        summary(TODAY - timedelta(days=30), "8"),
        summary(TODAY - timedelta(days=31), "16"),
        summary(TODAY - timedelta(days=60), "32"),
        summary(TODAY - timedelta(days=61), "64"),
        summary(TODAY, "5", Currency.EUR),
    ]
    assert aging(invoices, TODAY) == [
        Aging(Currency.CHF, chf("3"), chf("12"), chf("48"), chf("64")),
        Aging(
            Currency.EUR,
            Money(Decimal(5), Currency.EUR),
            Money.zero(Currency.EUR),
            Money.zero(Currency.EUR),
            Money.zero(Currency.EUR),
        ),
    ]


def test_expected_payments_per_week() -> None:
    monday = week_start(TODAY)
    assert monday == date(2026, 3, 9)
    assert week_start(monday) == monday
    invoices = [
        summary(TODAY - timedelta(days=40), "1"),  # overdue: this week
        summary(None, "2"),  # without due date: now
        summary(monday + timedelta(days=6), "4"),  # Sunday: this week
        summary(monday + timedelta(days=7), "8"),  # next Monday
        summary(monday + timedelta(weeks=5, days=6), "16"),  # last week shown
        summary(monday + timedelta(weeks=6), "32"),  # beyond
    ]
    weeks = expected_payments(invoices, TODAY)
    assert [week.week_start for week in weeks] == [
        monday + timedelta(weeks=offset) for offset in range(6)
    ]
    assert [week.amount for week in weeks] == [
        chf("7"),
        chf("8"),
        chf("0"),
        chf("0"),
        chf("0"),
        chf("16"),
    ]
    assert {week.currency for week in weeks} == {Currency.CHF}
    assert expected_payments([], TODAY) == []
    euro = expected_payments([summary(TODAY, "3", Currency.EUR), summary(TODAY, "1")], TODAY)
    assert [(week.currency, week.amount.amount) for week in euro][::6] == [
        (Currency.CHF, Decimal(1)),
        (Currency.EUR, Decimal(3)),
    ]
    assert all(isinstance(week, ExpectedWeek) for week in euro)


def test_quote_figures() -> None:
    open_quotes = [summary(TODAY, "100", status=DisplayStatus.SENT)]
    this_year = [
        summary(TODAY, "1", status=DisplayStatus.ACCEPTED),
        summary(TODAY, "1", status=DisplayStatus.ACCEPTED),
        summary(TODAY, "1", status=DisplayStatus.DECLINED),
        summary(TODAY, "1", status=DisplayStatus.EXPIRED),
        summary(TODAY, "1", Currency.EUR, status=DisplayStatus.ACCEPTED),
    ]
    assert quote_figures(open_quotes, this_year) == [
        QuoteFigures(Currency.CHF, chf("100"), 1, 2, 4),
        QuoteFigures(Currency.EUR, Money.zero(Currency.EUR), 0, 1, 1),
    ]
    assert quote_figures([], []) == []


def test_top_customers_per_currency() -> None:
    def revenue(net: str, currency: Currency = Currency.CHF) -> CustomerRevenue:
        return CustomerRevenue(new_id(), "Kunde", currency, Money(Decimal(net), currency))

    ranked = [revenue(str(100 - index)) for index in range(7)]
    euro = revenue("50", Currency.EUR)
    nothing = revenue("0")
    below = revenue("-5", Currency.EUR)
    shown = top_customers([*ranked[:3], euro, *ranked[3:], nothing, below])
    assert shown == [*ranked[:3], euro, *ranked[3:5]]


@pytest.mark.parametrize(
    ("days", "expected"),
    [([], None), ([3], 3), ([1, 2], 2), ([2, 3], 2), ([10, 20, 31], 20), ([0, 0, 1], 0)],
)
def test_average_days(days: list[int], expected: int | None) -> None:
    assert average_days(days) == expected


def test_the_overview_reads_every_page(
    documents: DocumentHandlers, dashboard: DashboardHandlers, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("rhinvoice.application.document.dashboard.MAX_PAGE_SIZE", 1)
    for day in (1, 2, 3):
        issued(documents, date(2026, 1, day))
    assert sum(item.open_amount.amount for item in [*dashboard.overview().overdue]) == Decimal(
        "324.30"
    )


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 3, 9), date(2025, 3, 9)),
        (date(2024, 2, 29), date(2023, 2, 28)),
        (date(2025, 2, 28), date(2024, 2, 28)),
        (date(2026, 12, 31), date(2025, 12, 31)),
    ],
)
def test_same_day_last_year(today: date, expected: date) -> None:
    assert same_day_last_year(today) == expected


def test_year_to_date_lists_every_currency() -> None:
    euro = Money(Decimal(5), Currency.EUR)
    assert year_to_date({Currency.CHF: chf("10")}, {Currency.EUR: euro}) == [
        YearToDate(Currency.CHF, chf("10"), chf("0")),
        YearToDate(Currency.EUR, Money.zero(Currency.EUR), euro),
    ]
    assert year_to_date({}, {}) == []


def test_overdue_invoices_per_currency() -> None:
    francs = [summary(TODAY - timedelta(days=60 - day)) for day in range(6)]
    euros = [summary(TODAY - timedelta(days=10), currency=Currency.EUR)]
    shown = first_per_currency([*francs, *euros], 5)
    assert shown == [*francs[:5], *euros]
    assert first_per_currency([], 5) == []


def test_days_to_pay_per_currency() -> None:
    assert days_to_pay(
        [(Currency.EUR, 10), (Currency.CHF, 3), (Currency.EUR, 21), (Currency.CHF, 5)]
    ) == [DaysToPay(Currency.CHF, 4), DaysToPay(Currency.EUR, 16)]
    assert days_to_pay([]) == []
