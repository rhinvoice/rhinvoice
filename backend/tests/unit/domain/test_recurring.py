"""Recurring invoice plans: dates, periods, the template."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rhinvoice.domain.document.lines import Discount, DocumentLine, LineKind, PriceMode
from rhinvoice.domain.recurring.plan import (
    Interval,
    InvoiceTemplate,
    PlanAction,
    RecurringPlan,
    add_months,
)
from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Currency
from tests.helpers import raises_exactly

NOW = datetime(2026, 1, 20, 9, 0, tzinfo=UTC)
TODAY = NOW.date()
HOSTING = DocumentLine(
    id=new_id(),
    kind=LineKind.ITEM,
    description="Hosting",
    quantity=Decimal(1),
    unit_price=Decimal(29),
)
TEMPLATE = InvoiceTemplate(currency=Currency.CHF, price_mode=PriceMode.NET, lines=(HOSTING,))


def plan(**overrides: object) -> RecurringPlan:
    values: dict[str, object] = {
        "name": "Hosting",
        "customer_id": new_id(),
        "interval": Interval.MONTHLY,
        "start_date": date(2026, 1, 31),
        "action": PlanAction.ISSUE,
        "template": TEMPLATE,
        "today": TODAY,
        "now": NOW,
    }
    values.update(overrides)
    return RecurringPlan.new(new_id(), **values)  # type: ignore[arg-type]  # test builder


def test_months_are_added_from_the_first_day() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2026, 1, 31), 2) == date(2026, 3, 31)
    assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)
    assert add_months(date(2026, 5, 1), 12) == date(2027, 5, 1)
    assert add_months(date(2026, 12, 1), 1) == date(2027, 1, 1)


def test_the_31st_stays_the_end_of_the_month() -> None:
    monthly = plan()
    assert monthly.next_date == date(2026, 1, 31)
    assert monthly.period() == (date(2026, 1, 31), date(2026, 2, 27))
    days: list[date] = []
    for _ in range(4):
        days.append(monthly.next_date)
        monthly = monthly.advance()
    assert days == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]


def test_the_last_period_ends_with_the_plan() -> None:
    ending = plan(start_date=date(2026, 1, 31), end_date=date(2026, 3, 15))
    assert ending.period() == (date(2026, 1, 31), date(2026, 2, 27))
    # The second invoice would cover up to 30 March; the plan ends on 15 March.
    assert ending.advance().period() == (date(2026, 2, 28), date(2026, 3, 15))


def test_intervals() -> None:
    assert [interval.months for interval in Interval] == [1, 3, 6, 12]
    quarterly = plan(interval=Interval.QUARTERLY, start_date=date(2026, 2, 1))
    assert quarterly.period() == (date(2026, 2, 1), date(2026, 4, 30))
    assert quarterly.advance().next_date == date(2026, 5, 1)
    yearly = plan(interval=Interval.YEARLY, start_date=date(2026, 3, 1))
    assert yearly.period() == (date(2026, 3, 1), date(2027, 2, 28))


@given(
    start=st.dates(min_value=date(2020, 1, 1), max_value=date(2035, 12, 31)),
    interval=st.sampled_from(Interval),
    count=st.integers(min_value=1, max_value=30),
)
def test_periods_follow_each_other_without_gap_or_overlap(
    start: date, interval: Interval, count: int
) -> None:
    current = plan(start_date=start, interval=interval, today=start)
    for index in range(count):
        first, last = current.period()
        assert first == add_months(start, index * interval.months)
        following = current.advance()
        assert following.next_date == last + timedelta(days=1)
        current = following


def test_when_a_plan_is_due() -> None:
    monthly = plan(start_date=TODAY)
    assert monthly.is_due(TODAY)
    assert not monthly.is_due(TODAY - timedelta(days=1))
    assert not monthly.pause().is_due(TODAY)
    ending = plan(start_date=TODAY, end_date=TODAY + timedelta(days=40))
    assert not ending.finished
    assert ending.advance().is_due(date(2026, 2, 20))
    finished = ending.advance().advance()
    assert finished.finished
    assert not finished.is_due(date(2027, 1, 1))
    with raises_exactly(InvalidStateError, "the plan has no invoice left"):
        finished.advance()
    # The last day itself still gets its invoice.
    assert plan(start_date=TODAY, end_date=TODAY).is_due(TODAY)


def test_resuming_skips_the_paused_invoices() -> None:
    paused = plan(start_date=TODAY).pause()
    assert not paused.active
    resumed = paused.resume(date(2026, 4, 5))
    assert (resumed.active, resumed.next_date) == (True, date(2026, 4, 20))
    with raises_exactly(InvalidStateError, "the plan is not paused") as running:
        resumed.resume(date(2026, 6, 1))
    assert running.value.code == "plan_not_paused"
    # Nothing to skip, and plans that end meanwhile stay finished.
    assert paused.resume(TODAY).next_date == TODAY
    ended = plan(start_date=TODAY, end_date=date(2026, 2, 1)).pause().resume(date(2026, 6, 1))
    assert ended.finished


def test_plan_rules() -> None:
    with raises_exactly(ValidationError, "the first invoice cannot be in the past") as past:
        plan(start_date=TODAY - timedelta(days=1))
    assert (past.value.field, past.value.code) == ("start_date", "plan_start_in_past")
    with raises_exactly(ValidationError, "the plan ends before it starts") as end:
        plan(end_date=date(2026, 1, 30))
    assert end.value.field == "end_date"
    with raises_exactly(ValidationError, "name is required"):
        plan(name=" ")
    assert plan(name=" Hosting ").name == "Hosting"
    with raises_exactly(ValidationError, "the next invoice is before the first one") as before:
        replace(plan(), next_date=date(2026, 1, 1))
    assert before.value.field == "next_date"
    created = plan()
    assert (created.created_at, created.service_period, created.active) == (NOW, True, True)
    assert created.pause().active is False


def test_changing_a_plan() -> None:
    running = plan(start_date=TODAY).advance()
    kept = running.change(
        name="Hosting Plus",
        customer_id=running.customer_id,
        interval=Interval.MONTHLY,
        start_date=TODAY,
        action=PlanAction.SEND,
        template=TEMPLATE,
        today=date(2026, 3, 1),
        end_date=date(2027, 1, 1),
        service_period=False,
    )
    # Same first day and interval: the counting goes on.
    assert (kept.name, kept.next_date, kept.action, kept.end_date, kept.service_period) == (
        "Hosting Plus",
        running.next_date,
        PlanAction.SEND,
        date(2027, 1, 1),
        False,
    )
    restarted = running.change(
        name="Hosting",
        customer_id=running.customer_id,
        interval=Interval.QUARTERLY,
        start_date=date(2026, 4, 1),
        action=PlanAction.ISSUE,
        template=TEMPLATE,
        today=date(2026, 3, 1),
    )
    assert (restarted.start_date, restarted.next_date) == (date(2026, 4, 1), date(2026, 4, 1))
    with raises_exactly(ValidationError, "the first invoice cannot be in the past") as past:
        running.change(
            name="Hosting",
            customer_id=running.customer_id,
            interval=Interval.YEARLY,
            start_date=TODAY,
            action=PlanAction.ISSUE,
            template=TEMPLATE,
            today=date(2026, 3, 1),
        )
    assert (past.value.field, past.value.code) == ("start_date", "plan_start_in_past")
    other = new_id()
    other_template = replace(TEMPLATE, subject="Neu")
    moved = running.change(
        name="Hosting",
        customer_id=other,
        interval=Interval.MONTHLY,
        start_date=TODAY,
        action=PlanAction.ISSUE,
        template=other_template,
        today=date(2026, 3, 1),
    )
    # The service period stays on unless switched off.
    assert (moved.customer_id, moved.template, moved.service_period) == (
        other,
        other_template,
        True,
    )


def test_template_rules() -> None:
    text = DocumentLine(id=new_id(), kind=LineKind.TEXT, description="Hosting")
    with raises_exactly(
        ValidationError, "the invoice needs at least one position with an amount"
    ) as empty:
        InvoiceTemplate(currency=Currency.CHF, price_mode=PriceMode.NET, lines=(text,))
    assert (empty.value.field, empty.value.code) == ("lines", "no_positions")
    with raises_exactly(ValidationError, "an invoice has at most 500 lines") as many:
        InvoiceTemplate(currency=Currency.CHF, price_mode=PriceMode.NET, lines=(HOSTING,) * 501)
    assert many.value.field == "lines"
    with raises_exactly(ValidationError, "a template has no frozen tax rates") as frozen:
        InvoiceTemplate(
            currency=Currency.CHF,
            price_mode=PriceMode.NET,
            lines=(replace(HOSTING, tax_rate=Decimal("8.1")),),
        )
    assert frozen.value.field == "lines"
    cleaned = InvoiceTemplate(
        currency=Currency.EUR,
        price_mode=PriceMode.GROSS,
        lines=(text, HOSTING),
        discount=Discount.none(),
        subject=" Hosting ",
        reference=" K-1 ",
        intro_text=" Hallo\r\n",
        payment_text=" Zahlbar ",
        closing_text=" Danke ",
    )
    assert (
        cleaned.subject,
        cleaned.reference,
        cleaned.intro_text,
        cleaned.payment_text,
        cleaned.closing_text,
    ) == ("Hosting", "K-1", "Hallo", "Zahlbar", "Danke")
    assert len(InvoiceTemplate(Currency.CHF, PriceMode.NET, (HOSTING,) * 500).lines) == 500
    with raises_exactly(ValidationError, "subject must be at most 200 characters long"):
        InvoiceTemplate(Currency.CHF, PriceMode.NET, (HOSTING,), subject="x" * 201)
    with raises_exactly(ValidationError, "reference must be at most 100 characters long"):
        InvoiceTemplate(Currency.CHF, PriceMode.NET, (HOSTING,), reference="x" * 101)
    with raises_exactly(ValidationError, "closing_text must be at most 4000 characters long"):
        InvoiceTemplate(Currency.CHF, PriceMode.NET, (HOSTING,), closing_text="x" * 4001)


@pytest.mark.parametrize("action", list(PlanAction))
def test_actions(action: PlanAction) -> None:
    assert plan(action=action).action is action
