"""Writing off invoices: the use cases, the list values and the bad debts per year."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from rhinvoice.application.document.bad_debts import BadDebtYear, bad_debts_by_year
from rhinvoice.application.document.dashboard import DashboardHandlers
from rhinvoice.application.document.handlers import (
    DocumentHandlers,
    PaymentInput,
    WriteOffInput,
)
from rhinvoice.application.document.ports import BadDebt, DocumentQuery
from rhinvoice.application.errors import NotFoundError
from rhinvoice.domain.document.document import (
    DisplayStatus,
    Document,
    DocumentEvent,
    DocumentStatus,
    DocumentType,
    EventKind,
)
from rhinvoice.domain.document.write_off import WriteOff, WriteOffReason
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Currency, Money
from tests.helpers import raises_exactly
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.application.test_document_handlers import draft_input
from tests.unit.domain import factories
from tests.unit.domain.test_imported_document import imported

TODAY = NOW.date()
LATER = NOW + timedelta(days=400)
GONE = WriteOffInput(written_off_on=TODAY, reason=WriteOffReason.GONE, note="Konkurs")


def chf(amount: str) -> Money:
    return Money(Decimal(amount), Currency.CHF)


@pytest.fixture
def handlers(store: Store, clock: FixedClock) -> DocumentHandlers:
    store.company = factories.company(payment_terms_days=30)
    account = factories.bank_account(is_default=True)
    store.bank_accounts[account.id] = account
    customer = factories.customer(id=UUID(int=1), payment_terms_days=None)
    store.customers[customer.id] = customer
    return DocumentHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)


def issued(handlers: DocumentHandlers) -> Document:
    draft = handlers.create(DocumentType.INVOICE, draft_input()).document
    return handlers.issue(draft.id).document


def test_writing_off_an_invoice(handlers: DocumentHandlers, store: Store) -> None:
    invoice = issued(handlers)
    handlers.add_payment(invoice.id, PaymentInput(paid_on=TODAY, amount="1000"))
    view = handlers.write_off(invoice.id, GONE)
    lost = view.document
    assert lost.status is DocumentStatus.WRITTEN_OFF
    assert view.display_status is DisplayStatus.WRITTEN_OFF
    assert lost.write_off is not None
    assert isinstance(lost.write_off.id, UUID)
    assert (
        lost.write_off.written_off_on,
        lost.write_off.amount,
        lost.write_off.reason,
        lost.write_off.note,
        lost.write_off.recorded_at,
    ) == (TODAY, chf("659.50"), WriteOffReason.GONE, "Konkurs", NOW)
    assert lost.events[-1] == DocumentEvent(
        NOW, EventKind.WRITTEN_OFF, f"659.50 {TODAY.isoformat()} gone"
    )
    index = store.documents[invoice.id].index
    assert index.open_amount == Money.zero(Currency.CHF)
    assert index.written_off == chf("659.50")
    assert handlers.get(invoice.id).document == lost


def test_open_invoices_have_nothing_written_off(handlers: DocumentHandlers, store: Store) -> None:
    invoice = issued(handlers)
    assert store.documents[invoice.id].index.written_off == Money.zero(Currency.CHF)


def test_the_write_off_is_not_dated_in_the_future(handlers: DocumentHandlers) -> None:
    invoice = issued(handlers)
    tomorrow = WriteOffInput(written_off_on=TODAY + timedelta(days=1), reason=WriteOffReason.OTHER)
    with raises_exactly(ValidationError, "the date of the write-off is in the future") as error:
        handlers.write_off(invoice.id, tomorrow)
    assert error.value.field == "written_off_on"
    assert error.value.code == "write_off_date_in_future"
    assert handlers.get(invoice.id).document.status is DocumentStatus.ISSUED
    today = WriteOffInput(written_off_on=TODAY, reason=WriteOffReason.OTHER)
    assert handlers.write_off(invoice.id, today).document.write_off is not None


def test_what_the_use_cases_refuse(handlers: DocumentHandlers) -> None:
    draft = handlers.create(DocumentType.INVOICE, draft_input()).document
    with raises_exactly(InvalidStateError, "a draft invoice cannot be written off"):
        handlers.write_off(draft.id, GONE)
    with raises_exactly(InvalidStateError, "a draft invoice cannot be reopened"):
        handlers.remove_write_off(draft.id)
    with raises_exactly(NotFoundError, "document not found"):
        handlers.write_off(new_id(), GONE)
    with raises_exactly(NotFoundError, "document not found"):
        handlers.remove_write_off(new_id())


def test_taking_a_write_off_back(handlers: DocumentHandlers, store: Store) -> None:
    invoice = issued(handlers)
    handlers.write_off(invoice.id, GONE)
    reopened = handlers.remove_write_off(invoice.id).document
    assert reopened.status is DocumentStatus.ISSUED
    assert reopened.write_off is None
    assert reopened.events[-1] == DocumentEvent(NOW, EventKind.WRITE_OFF_REMOVED, "1659.50")
    index = store.documents[invoice.id].index
    assert index.open_amount == chf("1659.50")
    assert index.written_off == Money.zero(Currency.CHF)


def test_a_payment_after_the_write_off(
    handlers: DocumentHandlers, store: Store, clock: FixedClock
) -> None:
    invoice = issued(handlers)
    handlers.write_off(invoice.id, GONE)
    clock.set(LATER)
    partly = handlers.add_payment(invoice.id, PaymentInput(paid_on=LATER.date(), amount="659.50"))
    assert partly.document.status is DocumentStatus.WRITTEN_OFF
    index = store.documents[invoice.id].index
    assert index.open_amount == Money.zero(Currency.CHF)
    assert index.written_off == chf("1000.00")
    whole = handlers.add_payment(invoice.id, PaymentInput(paid_on=LATER.date(), amount="1000"))
    assert whole.document.status is DocumentStatus.PAID
    assert store.documents[invoice.id].index.written_off == Money.zero(Currency.CHF)


def test_written_off_invoices_in_the_list(handlers: DocumentHandlers) -> None:
    lost = issued(handlers)
    handlers.write_off(lost.id, GONE)
    issued(handlers)
    query = DocumentQuery(today=TODAY + timedelta(days=99), types=frozenset({DocumentType.INVOICE}))
    facets = handlers.facets(query)
    assert facets.status_counts == {DisplayStatus.WRITTEN_OFF: 1, DisplayStatus.OVERDUE: 1}
    [sums] = facets.totals
    # The written-off invoice was invoiced, but nothing of it is open.
    assert (sums.count, sums.total, sums.open) == (2, chf("3319.00"), chf("1659.50"))
    found = handlers.search(
        DocumentQuery(
            today=TODAY + timedelta(days=99),
            types=frozenset({DocumentType.INVOICE}),
            statuses=frozenset({DisplayStatus.WRITTEN_OFF}),
        )
    )
    assert [(item.id, item.display_status, item.open_amount) for item in found.items] == [
        (lost.id, DisplayStatus.WRITTEN_OFF, Money.zero(Currency.CHF))
    ]


def test_the_dashboard_counts_what_was_written_off_neither_as_open_nor_as_paid(
    handlers: DocumentHandlers, store: Store, clock: FixedClock
) -> None:
    lost = issued(handlers)
    handlers.add_payment(lost.id, PaymentInput(paid_on=TODAY, amount="1000"))
    handlers.write_off(lost.id, GONE)
    clock.set(LATER)
    dashboard = DashboardHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)
    overview = dashboard.overview()
    [figures] = overview.figures
    assert (figures.open, figures.overdue, figures.paid) == (
        Money.zero(Currency.CHF),
        Money.zero(Currency.CHF),
        chf("1000.00"),
    )
    assert (figures.open_count, figures.overdue_count) == (0, 0)
    assert overview.aging == []
    assert overview.overdue == []
    # Paid after years: no measure of how customers pay.
    handlers.add_payment(lost.id, PaymentInput(paid_on=LATER.date(), amount="659.50"))
    after = dashboard.overview()
    assert after.days_to_pay == []
    assert after.figures[0].paid == chf("1659.50")


# --- Bad debts per year -----------------------------------------------------------------


def bad_debt(
    amount: str,
    on: date,
    *recoveries: tuple[date, str],
    total: str = "1296.00",
    net: str = "1200.00",
) -> BadDebt:
    invoice = imported(total=total, net=net, open_amount=total)
    return BadDebt(
        write_off=WriteOff(
            id=new_id(),
            written_off_on=on,
            amount=chf(amount),
            reason=WriteOffReason.GONE,
            recorded_at=NOW,
        ),
        totals=invoice.frozen_totals,
        recoveries=tuple((paid_on, chf(paid)) for paid_on, paid in recoveries),
    )


def test_no_write_offs_no_bad_debts() -> None:
    assert bad_debts_by_year([]) == []


def test_bad_debts_are_summed_per_year_of_the_write_off() -> None:
    years = bad_debts_by_year(
        [
            bad_debt("1296.00", date(2021, 12, 31)),
            bad_debt("648.00", date(2021, 3, 1)),
            bad_debt("20.00", date(2015, 12, 31), total="20.00", net="20.00"),
        ]
    )
    zero = Money.zero(Currency.CHF)
    assert years == [
        BadDebtYear(
            year=2021,
            currency=Currency.CHF,
            written_off=chf("1944.00"),
            recovered=zero,
            loss=chf("1944.00"),
            net=chf("1800.00"),
            tax=chf("144.00"),
        ),
        BadDebtYear(
            year=2015,
            currency=Currency.CHF,
            written_off=chf("20.00"),
            recovered=zero,
            loss=chf("20.00"),
            net=chf("20.00"),
            tax=zero,
        ),
    ]


def test_a_later_payment_counts_in_the_year_it_came_in() -> None:
    years = bad_debts_by_year(
        [bad_debt("1296.00", date(2021, 12, 31), (date(2023, 5, 2), "648.00"))]
    )
    zero = Money.zero(Currency.CHF)
    assert years == [
        BadDebtYear(
            year=2023,
            currency=Currency.CHF,
            written_off=zero,
            recovered=chf("648.00"),
            loss=chf("-648.00"),
            net=chf("-600.00"),
            tax=chf("-48.00"),
        ),
        BadDebtYear(
            year=2021,
            currency=Currency.CHF,
            written_off=chf("1296.00"),
            recovered=zero,
            loss=chf("1296.00"),
            net=chf("1200.00"),
            tax=chf("96.00"),
        ),
    ]


def test_a_payment_in_the_year_of_the_write_off_reduces_its_loss() -> None:
    [year] = bad_debts_by_year(
        [bad_debt("1296.00", date(2021, 3, 1), (date(2021, 9, 1), "296.00"))]
    )
    assert (year.written_off, year.recovered, year.loss) == (
        chf("1296.00"),
        chf("296.00"),
        chf("1000.00"),
    )
    assert (year.net, year.tax) == (chf("925.93"), chf("74.07"))


def test_currencies_are_kept_apart() -> None:
    euro = imported(total="1296.00", net="1200.00", open_amount="1296.00")
    totals = euro.frozen_totals
    eur = BadDebt(
        write_off=WriteOff(
            id=new_id(),
            written_off_on=date(2021, 1, 1),
            amount=Money(Decimal("10.00"), Currency.EUR),
            reason=WriteOffReason.SMALL_AMOUNT,
            recorded_at=NOW,
        ),
        totals=type(totals)(
            currency=Currency.EUR,
            lines=(),
            groups=(),
            subtotal=Money(Decimal("10.00"), Currency.EUR),
            discount=Money.zero(Currency.EUR),
            net=Money(Decimal("10.00"), Currency.EUR),
            tax=Money.zero(Currency.EUR),
            gross=Money(Decimal("10.00"), Currency.EUR),
            rounding=Money.zero(Currency.EUR),
            total=Money(Decimal("10.00"), Currency.EUR),
        ),
        recoveries=(),
    )
    years = bad_debts_by_year([eur, bad_debt("1296.00", date(2021, 6, 1))])
    assert [(year.year, year.currency, year.loss) for year in years] == [
        (2021, Currency.CHF, chf("1296.00")),
        (2021, Currency.EUR, Money(Decimal("10.00"), Currency.EUR)),
    ]


def test_the_bad_debts_of_the_installation(handlers: DocumentHandlers, clock: FixedClock) -> None:
    assert handlers.bad_debts() == []
    first = issued(handlers)
    second = issued(handlers)
    handlers.write_off(second.id, GONE)
    handlers.write_off(first.id, WriteOffInput(written_off_on=TODAY, reason=WriteOffReason.OTHER))
    clock.set(LATER)
    handlers.add_payment(first.id, PaymentInput(paid_on=LATER.date(), amount="659.50"))
    years = handlers.bad_debts()
    assert [(year.year, year.written_off, year.recovered) for year in years] == [
        (2027, Money.zero(Currency.CHF), chf("659.50")),
        (2026, chf("3319.00"), Money.zero(Currency.CHF)),
    ]
