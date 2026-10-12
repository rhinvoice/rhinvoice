"""Overview figures for the dashboard ("cockpit").

Per currency, since amounts in francs and euros are never added up:
revenue this year against last year, open and overdue invoices by age,
the payments to expect in the coming weeks, open quotes, the best customers
and how long customers take to pay.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from rhinvoice.application.common import MAX_PAGE_SIZE, PageRequest, SortDirection
from rhinvoice.application.document.ports import DocumentQuery, DocumentSort
from rhinvoice.domain.document.document import DisplayStatus, DocumentType
from rhinvoice.domain.shared.money import Money

if TYPE_CHECKING:
    from datetime import datetime

    from rhinvoice.application.document.ports import (
        CurrencyFigures,
        CustomerRevenue,
        DocumentSummary,
        MonthlyRevenue,
    )
    from rhinvoice.application.uow import UnitOfWork, UnitOfWorkFactory
    from rhinvoice.domain.shared.clock import Clock
    from rhinvoice.domain.shared.money import Currency

RECENT_EVENTS = 10
OVERDUE_SHOWN = 5
TOP_CUSTOMERS = 5
EXPECTED_WEEKS = 6
PAYMENT_DAYS_WINDOW = 365
AGE_LIMITS = (30, 60)
"""Overdue invoices are 1-30, 31-60 or more than 60 days late."""
_OPEN = frozenset({DisplayStatus.ISSUED, DisplayStatus.PARTIALLY_PAID, DisplayStatus.OVERDUE})
_DECIDED = frozenset({DisplayStatus.ACCEPTED, DisplayStatus.DECLINED, DisplayStatus.EXPIRED})


@dataclass(frozen=True, slots=True)
class Aging:
    """Open invoices of one currency by how late they are."""

    currency: Currency
    not_due: Money
    late_30: Money
    """1-30 days overdue."""
    late_60: Money
    """31-60 days overdue."""
    late_more: Money
    """More than 60 days overdue."""


@dataclass(frozen=True, slots=True)
class ExpectedWeek:
    """Open amounts falling due in a week; the first week includes everything overdue."""

    currency: Currency
    week_start: date
    """Monday of the week."""
    amount: Money


@dataclass(frozen=True, slots=True)
class QuoteFigures:
    currency: Currency
    open: Money
    """Sent quotes that are still valid."""
    open_count: int
    accepted: int
    """Quotes of this year accepted ..."""
    decided: int
    """... of all decided ones (accepted, declined or expired) of this year."""


@dataclass(frozen=True, slots=True)
class YearToDate:
    """Net revenue from 1 January to today, against last year up to the same day."""

    currency: Currency
    current: Money
    previous: Money


@dataclass(frozen=True, slots=True)
class DaysToPay:
    currency: Currency
    days: int
    """Average days from issuing to the last payment, over the last year."""


@dataclass(frozen=True, slots=True)
class Dashboard:
    today: date
    """In the installation's time zone (the browser's may differ)."""
    figures: list[CurrencyFigures]
    revenue: list[MonthlyRevenue]
    """Per month since January of last year: this year against last year."""
    year_to_date: list[YearToDate]
    recent: list[tuple[DocumentSummary, str, datetime]]
    aging: list[Aging]
    expected: list[ExpectedWeek]
    overdue: list[DocumentSummary]
    """The longest overdue invoices first, at most five per currency."""
    quotes: list[QuoteFigures]
    top_customers: list[CustomerRevenue]
    """This year's best customers per currency, at most five each."""
    days_to_pay: list[DaysToPay]


def week_start(day: date) -> date:
    """Monday of the day's week."""
    return day - timedelta(days=day.weekday())


def aging(invoices: list[DocumentSummary], today: date) -> list[Aging]:
    """Sum the open amounts per currency and age (days past the due date)."""
    buckets: dict[Currency, list[Money]] = {}
    for invoice in invoices:
        currency = invoice.currency
        sums = buckets.setdefault(currency, [Money.zero(currency)] * 4)
        late = 0 if invoice.due_date is None else (today - invoice.due_date).days
        index = (
            0 if late <= 0 else 1 if late <= AGE_LIMITS[0] else 2 if late <= AGE_LIMITS[1] else 3
        )
        sums[index] += invoice.open_amount
    return [Aging(currency, *buckets[currency]) for currency in sorted(buckets)]


def expected_payments(invoices: list[DocumentSummary], today: date) -> list[ExpectedWeek]:
    """Open amounts per currency and week of their due date, for the coming weeks."""
    first = week_start(today)
    weeks = [first + timedelta(weeks=offset) for offset in range(EXPECTED_WEEKS)]
    sums: dict[tuple[Currency, date], Money] = {}
    currencies: set[Currency] = set()
    for invoice in invoices:
        currencies.add(invoice.currency)
        due = invoice.due_date or today
        # Overdue amounts are expected now, the rest in the week they fall due.
        week = max(week_start(due), first)
        if week > weeks[-1]:
            continue
        key = (invoice.currency, week)
        sums[key] = sums.get(key, Money.zero(invoice.currency)) + invoice.open_amount
    return [
        ExpectedWeek(currency, week, sums.get((currency, week), Money.zero(currency)))
        for currency in sorted(currencies)
        for week in weeks
    ]


def quote_figures(
    open_quotes: list[DocumentSummary], this_year: list[DocumentSummary]
) -> list[QuoteFigures]:
    currencies = sorted({quote.currency for quote in [*open_quotes, *this_year]})
    result: list[QuoteFigures] = []
    for currency in currencies:
        mine = [quote for quote in open_quotes if quote.currency is currency]
        decided = [
            quote
            for quote in this_year
            if quote.currency is currency and quote.display_status in _DECIDED
        ]
        result.append(
            QuoteFigures(
                currency=currency,
                open=sum((quote.total for quote in mine), Money.zero(currency)),
                open_count=len(mine),
                accepted=sum(
                    1 for quote in decided if quote.display_status is DisplayStatus.ACCEPTED
                ),
                decided=len(decided),
            )
        )
    return result


def top_customers(revenue: list[CustomerRevenue]) -> list[CustomerRevenue]:
    """Pick the best customers of each currency (ranked by the repository), revenue above 0."""
    shown: dict[Currency, int] = {}
    result: list[CustomerRevenue] = []
    for entry in revenue:
        if entry.net.amount <= 0 or shown.get(entry.currency, 0) >= TOP_CUSTOMERS:
            continue
        shown[entry.currency] = shown.get(entry.currency, 0) + 1
        result.append(entry)
    return result


def same_day_last_year(today: date) -> date:
    """Go back to the same day a year ago; 29 February becomes the 28th."""
    day = min(today.day, 28) if (today.month, today.day) == (2, 29) else today.day
    return date(today.year - 1, today.month, day)


def year_to_date(
    current: dict[Currency, Money], previous: dict[Currency, Money]
) -> list[YearToDate]:
    return [
        YearToDate(
            currency,
            current.get(currency, Money.zero(currency)),
            previous.get(currency, Money.zero(currency)),
        )
        for currency in sorted(current.keys() | previous.keys())
    ]


def first_per_currency(summaries: list[DocumentSummary], limit: int) -> list[DocumentSummary]:
    """Keep the first ``limit`` documents of each currency, in their order."""
    shown: dict[Currency, int] = {}
    result: list[DocumentSummary] = []
    for summary in summaries:
        if shown.get(summary.currency, 0) < limit:
            shown[summary.currency] = shown.get(summary.currency, 0) + 1
            result.append(summary)
    return result


def days_to_pay(payments: list[tuple[Currency, int]]) -> list[DaysToPay]:
    """Average the days per currency."""
    by_currency: dict[Currency, list[int]] = {}
    for currency, days in payments:
        by_currency.setdefault(currency, []).append(days)
    return [
        DaysToPay(currency, average)
        for currency in sorted(by_currency)
        if (average := average_days(by_currency[currency])) is not None
    ]


def average_days(days: list[int]) -> int | None:
    """Round the average to whole days (half to even); None without paid invoices."""
    if not days:
        return None
    return int((Decimal(sum(days)) / len(days)).to_integral_value())


@dataclass(frozen=True, slots=True)
class DashboardHandlers:
    uow: UnitOfWorkFactory
    clock: Clock

    def overview(self) -> Dashboard:
        today = self.clock.today()
        this_year = date(today.year, 1, 1)
        with self.uow() as uow:
            open_invoices = _all(uow, today, DocumentType.INVOICE, _OPEN, year=None)
            overdue = [
                invoice
                for invoice in open_invoices
                if invoice.display_status is DisplayStatus.OVERDUE
            ]
            return Dashboard(
                today=today,
                figures=uow.documents.figures(today),
                revenue=uow.documents.revenue_by_month(date(today.year - 1, 1, 1)),
                year_to_date=year_to_date(
                    uow.documents.revenue_between(this_year, today),
                    uow.documents.revenue_between(
                        date(today.year - 1, 1, 1), same_day_last_year(today)
                    ),
                ),
                recent=uow.documents.recent_events(RECENT_EVENTS, today),
                aging=aging(open_invoices, today),
                expected=expected_payments(open_invoices, today),
                overdue=first_per_currency(overdue, OVERDUE_SHOWN),
                quotes=quote_figures(
                    _all(uow, today, DocumentType.QUOTE, frozenset({DisplayStatus.SENT}), None),
                    _all(uow, today, DocumentType.QUOTE, _DECIDED, year=today.year),
                ),
                top_customers=top_customers(uow.documents.revenue_by_customer(this_year)),
                days_to_pay=days_to_pay(
                    uow.documents.days_to_pay(today - timedelta(days=PAYMENT_DAYS_WINDOW))
                ),
            )


def _all(
    uow: UnitOfWork,
    today: date,
    document_type: DocumentType,
    statuses: frozenset[DisplayStatus],
    year: int | None,
) -> list[DocumentSummary]:
    """Every document of the selection, the earliest due first."""
    found: list[DocumentSummary] = []
    while True:
        page = uow.documents.search(
            DocumentQuery(
                today=today,
                types=frozenset({document_type}),
                statuses=statuses,
                year=year,
                sort=DocumentSort.DUE_DATE,
                direction=SortDirection.ASC,
                page=PageRequest(limit=MAX_PAGE_SIZE, offset=len(found)),
            )
        )
        found.extend(page.items)
        if len(found) >= page.total or not page.items:
            return found
