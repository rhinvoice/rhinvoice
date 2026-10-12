from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from rhinvoice.application.document.handlers import DocumentHandlers, DraftInput, LineInput
from rhinvoice.application.errors import ConflictError
from rhinvoice.application.numbering.handlers import (
    ConfigureSequence,
    NumberingHandlers,
    allocate_number,
)
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import LineKind
from rhinvoice.domain.numbering.sequence import NumberSequence, SequenceKind
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.errors import ValidationError
from tests.helpers import raises_exactly
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories


@pytest.fixture
def handlers(store: Store, clock: FixedClock) -> NumberingHandlers:
    return NumberingHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)


def test_list_returns_defaults_for_every_kind(handlers: NumberingHandlers) -> None:
    views = {view.sequence.kind: view for view in handlers.list()}
    assert set(views) == set(SequenceKind)
    assert views[SequenceKind.INVOICE].next_number == "R20260001"
    assert views[SequenceKind.INVOICE].next_counter == 1
    assert views[SequenceKind.CUSTOMER].next_number == "1001"
    assert [view.sequence.kind for view in handlers.list()] == list(SequenceKind)


def test_configure_and_preview(handlers: NumberingHandlers, store: Store) -> None:
    command = ConfigureSequence(
        kind=SequenceKind.INVOICE,
        pattern=" RE-{YY}-{NNNNN} ",
        start_value=1,
        yearly_reset=True,
        next_value=345,
    )
    assert handlers.preview(command) == "RE-26-00345"
    assert store.sequences == {}
    view = handlers.configure(command)
    assert view.next_number == "RE-26-00345"
    assert view.next_counter == 345
    assert store.sequences[SequenceKind.INVOICE].pattern == "RE-{YY}-{NNNNN}"
    listed = {v.sequence.kind: v for v in handlers.list()}
    assert listed[SequenceKind.INVOICE].next_number == "RE-26-00345"


def test_configure_locks_the_sequence(store: Store, clock: FixedClock) -> None:
    locked: list[SequenceKind] = []

    class Spy(InMemoryUnitOfWork):
        def commit(self) -> None:
            locked.extend(self.sequences.locked)
            super().commit()

    handlers = NumberingHandlers(uow=lambda: Spy(store), clock=clock)
    handlers.configure(
        ConfigureSequence(
            kind=SequenceKind.QUOTE,
            pattern="A{YY}{NNN}",
            start_value=1,
            yearly_reset=True,
            next_value=1,
        ),
    )
    assert locked == [SequenceKind.QUOTE]


def test_listed_counter_reflects_a_pending_yearly_reset(store: Store) -> None:
    with InMemoryUnitOfWork(store) as uow:
        allocate_number(
            uow, SequenceKind.INVOICE, FixedClock(datetime(2025, 12, 1, tzinfo=UTC)).today()
        )
        uow.commit()
    clock = FixedClock(datetime(2026, 1, 2, 12, 0, tzinfo=UTC))
    handlers = NumberingHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)
    view = {v.sequence.kind: v for v in handlers.list()}[SequenceKind.INVOICE]
    assert view.next_counter == 1
    assert view.sequence.next_value == 2
    assert view.next_number == "R20260001"


def test_configure_rejects_invalid_patterns(handlers: NumberingHandlers, store: Store) -> None:
    with pytest.raises(ValidationError):
        handlers.configure(
            ConfigureSequence(
                kind=SequenceKind.QUOTE,
                pattern="{NNNN}",
                start_value=1,
                yearly_reset=True,
                next_value=1,
            ),
        )
    assert store.sequences == {}


def test_allocate_number_locks_and_advances(store: Store, clock: FixedClock) -> None:
    with InMemoryUnitOfWork(store) as uow:
        assert allocate_number(uow, SequenceKind.INVOICE, clock.today()) == "R20260001"
        assert allocate_number(uow, SequenceKind.INVOICE, clock.today()) == "R20260002"
        assert uow.sequences.locked == [SequenceKind.INVOICE, SequenceKind.INVOICE]
        uow.commit()
    assert store.sequences[SequenceKind.INVOICE].next_value == 3


def test_allocate_number_uses_the_stored_sequence(store: Store) -> None:
    store.sequences[SequenceKind.CUSTOMER] = NumberSequence.default(
        SequenceKind.CUSTOMER
    ).reconfigure(
        pattern="K{NNN}",
        start_value=1,
        yearly_reset=False,
        next_value=42,
        on=date(2026, 1, 1),
    )
    clock = FixedClock(datetime(2027, 1, 1, tzinfo=UTC))
    with InMemoryUnitOfWork(store) as uow:
        assert allocate_number(uow, SequenceKind.CUSTOMER, clock.today()) == "K042"


def test_configure_refuses_numbers_that_are_already_used(
    handlers: NumberingHandlers, store: Store
) -> None:
    customer = factories.customer(number="1001")
    store.customers[customer.id] = customer
    command = ConfigureSequence(
        kind=SequenceKind.CUSTOMER,
        pattern="{NNNN}",
        start_value=1001,
        yearly_reset=False,
        next_value=1001,
    )
    with raises_exactly(ConflictError, "the number 1001 is already in use") as error:
        handlers.configure(command)
    assert error.value.details == {"next_value": "the number 1001 is already in use"}
    assert handlers.configure(replace(command, next_value=1002)).next_number == "1002"


def test_configure_checks_articles_and_documents(handlers: NumberingHandlers) -> None:
    for kind in (SequenceKind.ARTICLE, SequenceKind.INVOICE):
        view = handlers.configure(
            ConfigureSequence(
                kind=kind, pattern="X{YY}{NNN}", start_value=1, yearly_reset=True, next_value=5
            ),
        )
        assert view.next_number == "X26005"


def test_configure_refuses_used_article_and_document_numbers(
    handlers: NumberingHandlers, store: Store, clock: FixedClock
) -> None:
    article = factories.article(number="5")
    store.articles[article.id] = article
    with raises_exactly(ConflictError, "the number 5 is already in use"):
        handlers.configure(
            ConfigureSequence(
                kind=SequenceKind.ARTICLE,
                pattern="{N}",
                start_value=1,
                yearly_reset=False,
                next_value=5,
            ),
        )
    store.company = factories.company()
    account = factories.bank_account(is_default=True)
    store.bank_accounts[account.id] = account
    customer = factories.customer()
    store.customers[customer.id] = customer
    documents = DocumentHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)
    line = LineInput(kind=LineKind.ITEM, description="Beratung", unit_price="100")
    invoice = documents.create(
        DocumentType.INVOICE, DraftInput(customer_id=customer.id, lines=(line,))
    )
    assert documents.issue(invoice.document.id).document.number == "R20260001"
    with raises_exactly(ConflictError, "the number R20260001 is already in use"):
        handlers.configure(
            ConfigureSequence(
                kind=SequenceKind.INVOICE,
                pattern="R{YYYY}{NNNN}",
                start_value=1,
                yearly_reset=True,
                next_value=1,
            ),
        )


def test_configure_validates_the_number_length(handlers: NumberingHandlers) -> None:
    with pytest.raises(ValidationError):
        handlers.configure(
            ConfigureSequence(
                kind=SequenceKind.CUSTOMER,
                pattern="KUNDE-{YYYY}-{NNNNNNNNNNNN}",
                start_value=1,
                yearly_reset=False,
                next_value=1,
            ),
        )
