"""Overdue invoices, their reminders and the dunning levels."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from rhinvoice.application.document.handlers import DocumentHandlers, DraftInput, LineInput
from rhinvoice.application.dunning.handlers import DunningHandlers
from rhinvoice.application.errors import NotFoundError
from rhinvoice.domain.document.document import DocumentType, EventKind
from rhinvoice.domain.document.lines import LineKind
from rhinvoice.domain.dunning.reminder import DEFAULT_LEVELS, NextReminder
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Currency, Money
from tests.helpers import raises_exactly
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories

CUSTOMER = UUID(int=1)
LINE = LineInput(kind=LineKind.ITEM, description="Beratung", quantity="1", unit_price="100")
TODAY = NOW.date()


@pytest.fixture
def documents(store: Store, clock: FixedClock) -> DocumentHandlers:
    store.company = factories.company()
    account = factories.bank_account(is_default=True)
    store.bank_accounts[account.id] = account
    store.customers[CUSTOMER] = factories.customer(id=CUSTOMER)
    return DocumentHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)


@pytest.fixture
def dunning(store: Store, clock: FixedClock, documents: DocumentHandlers) -> DunningHandlers:
    return DunningHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock, documents=documents)


def invoice(documents: DocumentHandlers, due: date, issued: date | None = None) -> UUID:
    draft = DraftInput(
        customer_id=CUSTOMER,
        lines=(LINE,),
        issue_date=issued or due - timedelta(days=30),
        due_date=due,
    )
    created = documents.create(DocumentType.INVOICE, draft).document.id
    documents.issue(created)
    return created


def test_the_overview_lists_overdue_invoices_longest_overdue_first(
    documents: DocumentHandlers, dunning: DunningHandlers
) -> None:
    # Issued in the other order: the overview sorts by the due date.
    newer = invoice(documents, TODAY - timedelta(days=3), TODAY - timedelta(days=30))
    older = invoice(documents, TODAY - timedelta(days=20), TODAY - timedelta(days=29))
    invoice(documents, TODAY + timedelta(days=5))
    items = dunning.overview()
    assert [item.invoice.id for item in items] == [older, newer]
    assert items[0].next == NextReminder(
        level=1,
        due_on=TODAY - timedelta(days=13),
        fee=Money(Decimal("0.00"), Currency.CHF),
        deadline=TODAY + timedelta(days=10),
    )
    assert items[0].reminders == ()


def test_writing_reminders(
    documents: DocumentHandlers, dunning: DunningHandlers, store: Store
) -> None:
    overdue = invoice(documents, TODAY - timedelta(days=20))
    reminder, view = dunning.remind(overdue, level=1)
    assert (reminder.level, reminder.issued_on, reminder.due_date) == (
        1,
        TODAY,
        TODAY + timedelta(days=10),
    )
    assert view.document.events[-1].kind is EventKind.REMINDED
    assert (view.document.events[-1].at, reminder.created_at) == (NOW, NOW)
    assert store.documents[overdue].document.events[-1].detail == "1"
    assert dunning.get(reminder.id) == reminder
    assert reminder.text == DEFAULT_LEVELS[0].text_de
    # A second click on the same level writes nothing more.
    with raises_exactly(InvalidStateError, "the next reminder is level 2, not 1"):
        dunning.remind(overdue, level=1)
    # The second level is due a week after the first deadline: only on purpose today.
    with raises_exactly(
        InvalidStateError, f"level 2 is due on {reminder.due_date + timedelta(days=7)}"
    ):
        dunning.remind(overdue, level=2)
    second, _ = dunning.remind(overdue, level=2, early=True)
    assert dunning.reminders(overdue) == [reminder, second]
    [item] = dunning.overview()
    assert (item.reminders, item.next) == (
        (reminder, second),
        NextReminder(
            level=3,
            due_on=second.due_date + timedelta(days=7),
            fee=Money(Decimal("0.00"), Currency.CHF),
            deadline=TODAY + timedelta(days=7),
        ),
    )
    dunning.remind(overdue, level=3, early=True)
    with raises_exactly(InvalidStateError, "only overdue invoices get a reminder, at most three"):
        dunning.remind(overdue, level=3, early=True)
    with raises_exactly(NotFoundError, "document not found"):
        dunning.reminders(new_id())


def test_reminders_need_an_overdue_invoice(
    documents: DocumentHandlers, dunning: DunningHandlers
) -> None:
    with raises_exactly(NotFoundError, "document not found"):
        dunning.remind(new_id(), level=1)
    with raises_exactly(NotFoundError, "reminder not found"):
        dunning.get(new_id())
    not_due = invoice(documents, TODAY + timedelta(days=1))
    with raises_exactly(InvalidStateError, "only overdue invoices get a reminder, at most three"):
        dunning.remind(not_due, level=1, early=True)
    assert dunning.reminders(not_due) == []


def test_levels(dunning: DunningHandlers, store: Store) -> None:
    assert dunning.levels() == list(DEFAULT_LEVELS)
    changed = [replace(level, fee=Decimal("5.00")) for level in reversed(DEFAULT_LEVELS)]
    saved = dunning.save_levels(changed)
    assert [level.level for level in saved] == [1, 2, 3]
    assert [level.fee for level in dunning.levels()] == [Decimal("5.00")] * 3
    assert store.dunning_levels == saved
    with raises_exactly(ValidationError, "each of the three levels once") as caught:
        dunning.save_levels(changed[:2])
    assert (caught.value.field, caught.value.code) == ("levels", "levels_incomplete")
    with raises_exactly(ValidationError, "each of the three levels once"):
        dunning.save_levels([*changed[:2], changed[0]])


def test_the_overview_reads_every_page(
    documents: DocumentHandlers, dunning: DunningHandlers, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("rhinvoice.application.dunning.handlers.MAX_PAGE_SIZE", 1)
    ids = [invoice(documents, TODAY - timedelta(days=days)) for days in (9, 8, 7)]
    assert [item.invoice.id for item in dunning.overview()] == ids
