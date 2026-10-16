# ruff: noqa: RUF001 - French and Italian elide with the typographic apostrophe.
"""Payment reminders: when the next level is due and what it asks for."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from rhinvoice.domain.document.document import DocumentType, EventKind
from rhinvoice.domain.dunning.reminder import (
    DEFAULT_LEVELS,
    Dunning,
    DunningLevel,
    NextReminder,
    Reminder,
)
from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency, Money
from tests.helpers import raises_exactly
from tests.unit.domain.test_document import NOW, TODAY, issued, pay

DUE = TODAY + timedelta(days=30)
"""The due date of the issued test invoice."""


def test_the_first_reminder_is_due_a_week_after_the_due_date() -> None:
    dunning = Dunning(issued())
    assert dunning.next(DEFAULT_LEVELS, DUE) is None
    upcoming = dunning.next(DEFAULT_LEVELS, DUE + timedelta(days=1))
    assert upcoming == NextReminder(
        level=1,
        due_on=DUE + timedelta(days=7),
        fee=Money(Decimal("0.00"), Currency.CHF),
        deadline=DUE + timedelta(days=11),
    )
    assert upcoming is not None
    assert not upcoming.is_due(DUE + timedelta(days=6))
    assert upcoming.is_due(DUE + timedelta(days=7))


def test_a_reminder_sets_a_new_deadline_and_keeps_the_open_amount() -> None:
    invoice = pay(issued(), "100")
    today = DUE + timedelta(days=8)
    reminder = Dunning(invoice).remind(
        DEFAULT_LEVELS, level=1, early=False, reminder_id=new_id(), today=today, now=NOW
    )
    assert (reminder.level, reminder.issued_on, reminder.due_date) == (
        1,
        today,
        today + timedelta(days=10),
    )
    assert reminder.open_amount == invoice.open_amount()
    assert reminder.fee == Money(Decimal("0.00"), Currency.CHF)
    assert reminder.total == invoice.open_amount()
    assert (reminder.invoice_id, reminder.created_at) == (invoice.id, NOW)
    # The text is kept, in the invoice's language.
    assert reminder.text == DEFAULT_LEVELS[0].text_de


WITH_FEES = tuple(
    replace(level, fee=Decimal(fee))
    for level, fee in zip(DEFAULT_LEVELS, ("0", "20", "30"), strict=True)
)


def test_later_levels_count_from_the_previous_deadline_and_add_a_fee() -> None:
    invoice = issued()
    first_day = DUE + timedelta(days=8)

    def remind(dunning: Dunning, level: int) -> Reminder:
        return dunning.remind(
            WITH_FEES, level=level, early=True, reminder_id=new_id(), today=first_day, now=NOW
        )

    first = remind(Dunning(invoice), 1)
    dunning = Dunning(invoice, (first,))
    upcoming = dunning.next(WITH_FEES, first_day)
    assert upcoming == NextReminder(
        level=2,
        due_on=first.due_date + timedelta(days=7),
        fee=Money(Decimal(20), Currency.CHF),
        deadline=first_day + timedelta(days=10),
    )
    second = remind(dunning, 2)
    assert second.fee == Money(Decimal(20), Currency.CHF)
    assert second.total == invoice.open_amount() + Money(Decimal(20), Currency.CHF)
    third = remind(Dunning(invoice, (first, second)), 3)
    assert (third.level, third.fee.amount, third.due_date) == (
        3,
        Decimal(30),
        first_day + timedelta(days=7),
    )
    done = Dunning(invoice, (third, first, second))
    assert done.next(WITH_FEES, first_day) is None
    with raises_exactly(
        InvalidStateError, "only overdue invoices get a reminder, at most three"
    ) as caught:
        remind(done, 3)
    assert caught.value.code == "not_remindable"


def test_only_the_expected_level_is_written() -> None:
    today = DUE + timedelta(days=8)
    with raises_exactly(InvalidStateError, "the next reminder is level 1, not 2") as caught:
        Dunning(issued()).remind(
            DEFAULT_LEVELS, level=2, early=False, reminder_id=new_id(), today=today, now=NOW
        )
    assert caught.value.code == "reminder_level_changed"


def test_a_level_before_its_day_is_written_only_on_purpose() -> None:
    today = DUE + timedelta(days=6)
    with raises_exactly(
        InvalidStateError, f"level 1 is due on {DUE + timedelta(days=7)}"
    ) as caught:
        Dunning(issued()).remind(
            DEFAULT_LEVELS, level=1, early=False, reminder_id=new_id(), today=today, now=NOW
        )
    assert caught.value.code == "reminder_not_due"
    early = Dunning(issued()).remind(
        DEFAULT_LEVELS, level=1, early=True, reminder_id=new_id(), today=today, now=NOW
    )
    assert early.issued_on == today


@pytest.mark.parametrize("language", list(Language))
def test_reminders_keep_the_text_of_the_invoice_language(language: Language) -> None:
    invoice = issued(language=language)
    reminder = Dunning(invoice).remind(
        DEFAULT_LEVELS,
        level=1,
        early=True,
        reminder_id=new_id(),
        today=DUE + timedelta(days=1),
        now=NOW,
    )
    assert reminder.text == DEFAULT_LEVELS[0].text(language)
    texts = {getattr(DEFAULT_LEVELS[0], f"text_{other.value}") for other in Language}
    assert len(texts) == len(Language), "every language has its own text"


@pytest.mark.parametrize("change", ["paid", "quote", "cancelled", "draft"])
def test_only_open_overdue_invoices_get_reminders(change: str) -> None:
    late = DUE + timedelta(days=30)
    invoice = issued()
    if change == "paid":
        invoice = pay(invoice, str(invoice.open_amount().amount))
    elif change == "quote":
        invoice = issued(DocumentType.QUOTE)
    elif change == "cancelled":
        invoice = replace(invoice, status=invoice.status.CANCELLED)
    else:
        invoice = replace(invoice, status=invoice.status.DRAFT)
    assert Dunning(invoice).next(DEFAULT_LEVELS, late) is None


def test_invoices_without_a_due_date_are_never_overdue() -> None:
    invoice = issued()
    undated = replace(invoice, content=replace(invoice.content, due_date=None))
    assert Dunning(undated).next(DEFAULT_LEVELS, DUE + timedelta(days=100)) is None


def test_a_level_that_is_not_configured() -> None:
    with raises_exactly(ValidationError, "level 1 is not configured"):
        Dunning(issued()).next(DEFAULT_LEVELS[1:], DUE + timedelta(days=1))


def test_the_invoice_history_names_the_reminder() -> None:
    reminded = issued().record_reminder(2, NOW)
    assert (reminded.events[-1].kind, reminded.events[-1].detail) == (EventKind.REMINDED, "2")
    with raises_exactly(InvalidStateError, "a paid invoice cannot be reminded"):
        pay(issued(), str(issued().open_amount().amount)).record_reminder(1, NOW)


LEVEL = DEFAULT_LEVELS[0]


@pytest.mark.parametrize(
    ("changes", "field", "message"),
    [
        ({"level": 4}, "level", "the level must be one of (1, 2, 3)"),
        ({"days_after_due": -1}, "days_after_due", "must be between 0 and 365 days"),
        ({"days_after_due": 366}, "days_after_due", "must be between 0 and 365 days"),
        ({"payment_days": 0}, "payment_days", "must be between 1 and 365 days"),
        ({"payment_days": 366}, "payment_days", "must be between 1 and 365 days"),
        ({"fee": Decimal(-1)}, "fee", "the fee must be between 0 and 1000 in steps of 0.05"),
        ({"fee": Decimal("1000.05")}, "fee", "the fee must be between 0 and 1000 in steps of 0.05"),
        ({"fee": Decimal("12.33")}, "fee", "the fee must be between 0 and 1000 in steps of 0.05"),
        ({"text_de": "x" * 2001}, "text_de", "text_de must be at most 2000 characters long"),
        ({"text_fr": "x" * 2001}, "text_fr", "text_fr must be at most 2000 characters long"),
        ({"text_it": "x" * 2001}, "text_it", "text_it must be at most 2000 characters long"),
    ],
)
def test_levels_are_validated(changes: dict[str, object], field: str, message: str) -> None:
    with raises_exactly(ValidationError, message) as caught:
        replace(LEVEL, **changes)  # type: ignore[arg-type]  # test builder
    assert caught.value.field == field


def test_level_texts_are_cleaned_and_limits_are_inclusive() -> None:
    level = DunningLevel(
        level=3,
        days_after_due=365,
        payment_days=365,
        fee=Decimal("1000.00"),
        text_de=" Bitte \r\n",
        text_en="",
        text_fr=" S’il vous plaît\r\n",
        text_it="\tPer favore ",
    )
    assert (level.text_de, level.days_after_due) == ("Bitte", 365)
    assert (level.text_fr, level.text_it) == ("S’il vous plaît", "Per favore")
    assert replace(LEVEL, days_after_due=0, payment_days=1, fee=Decimal(0)).payment_days == 1
    assert replace(LEVEL, fee=Decimal("12.35")).fee == Decimal("12.35")
