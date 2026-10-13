"""Write-offs in PostgreSQL: round trip, protection, list, figures and bad debts."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from rhinvoice.application.document.handlers import (
    DocumentHandlers,
    PaymentInput,
    WriteOffInput,
)
from rhinvoice.application.document.ports import DocumentQuery
from rhinvoice.domain.document.document import DisplayStatus, DocumentStatus, DocumentType
from rhinvoice.domain.document.write_off import WriteOffReason
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.money import Currency, Money
from rhinvoice.infrastructure.db.uow import SqlUnitOfWork
from tests.integration.test_document_persistence import FOOD, NOW, TODAY, draft, setup

__all__ = ["setup"]

LATER = NOW + timedelta(days=400)
GONE = WriteOffInput(written_off_on=TODAY, reason=WriteOffReason.GONE, note="Konkurs")


def chf(amount: str) -> Money:
    return Money(Decimal(amount), Currency.CHF)


def issued(handlers: DocumentHandlers, customer: UUID, **overrides: object) -> UUID:
    created = handlers.create(DocumentType.INVOICE, draft(customer, **overrides)).document
    return handlers.issue(created.id).document.id


def test_round_trip_of_a_write_off(setup: tuple[DocumentHandlers, UUID, FixedClock]) -> None:
    handlers, customer, clock = setup
    invoice = issued(handlers, customer)
    handlers.add_payment(invoice, PaymentInput(paid_on=TODAY, amount="1000"))
    written = handlers.write_off(invoice, GONE).document
    loaded = handlers.get(invoice).document
    assert loaded == written
    assert loaded.status is DocumentStatus.WRITTEN_OFF
    assert loaded.write_off is not None
    assert (loaded.write_off.amount, loaded.write_off.reason, loaded.write_off.note) == (
        chf("659.50"),
        WriteOffReason.GONE,
        "Konkurs",
    )
    assert loaded.write_off.amount.amount.as_tuple().exponent == -2
    # Saved again (a later payment): the stored write-off is kept as it is.
    clock.set(LATER)
    handlers.add_payment(invoice, PaymentInput(paid_on=LATER.date(), amount="59.50"))
    after = handlers.get(invoice).document
    assert after.write_off == written.write_off
    assert after.written_off_amount == chf("600.00")
    assert after.recoveries == (after.payments[1],)
    handlers.remove_payment(invoice, after.payments[1].id)
    reopened = handlers.remove_write_off(invoice).document
    assert handlers.get(invoice).document == reopened
    assert reopened.write_off is None
    assert reopened.status is DocumentStatus.PARTIALLY_PAID
    # Written off once more: a new write-off replaces nothing that is stored.
    again = handlers.write_off(invoice, GONE).document
    assert handlers.get(invoice).document.write_off == again.write_off
    assert again.write_off != written.write_off


def test_write_offs_are_protected(
    engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    handlers, customer, _ = setup
    invoice = issued(handlers, customer)
    handlers.write_off(invoice, GONE)
    with (
        engine.begin() as connection,
        pytest.raises(IntegrityError, match="write-offs cannot be changed, only removed"),
    ):
        connection.execute(
            text("UPDATE document_write_offs SET amount = 1 WHERE document_id = :id"),
            {"id": invoice},
        )
    insert = text(
        "INSERT INTO document_write_offs (id, document_id, written_off_on, amount, reason,"
        " recorded_at) VALUES (gen_random_uuid(), :id, :day, :amount, 'other', now())"
    )
    # One write-off per invoice, and never of nothing.
    with engine.begin() as connection, pytest.raises(IntegrityError, match="uq_document_write"):
        connection.execute(insert, {"id": invoice, "day": TODAY, "amount": 5})
    other = issued(handlers, customer)
    with engine.begin() as connection, pytest.raises(IntegrityError, match="amount_positive"):
        connection.execute(insert, {"id": other, "day": TODAY, "amount": 0})
    # The invoice itself stays frozen.
    with engine.begin() as connection, pytest.raises(IntegrityError, match="immutable"):
        connection.execute(
            text("UPDATE documents SET subject = 'x' WHERE id = :id"), {"id": invoice}
        )


def test_written_off_invoices_in_list_and_figures(
    engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    handlers, customer, clock = setup
    lost = issued(handlers, customer)
    handlers.add_payment(lost, PaymentInput(paid_on=TODAY, amount="1000"))
    handlers.write_off(lost, GONE)
    open_one = issued(handlers, customer, lines=(FOOD,))
    late = TODAY + timedelta(days=99)
    invoices = frozenset({DocumentType.INVOICE})

    found = handlers.search(
        DocumentQuery(today=late, types=invoices, statuses=frozenset({DisplayStatus.WRITTEN_OFF}))
    )
    assert [(item.id, item.display_status, item.open_amount) for item in found.items] == [
        (lost, DisplayStatus.WRITTEN_OFF, chf("0.00"))
    ]
    overdue = handlers.search(
        DocumentQuery(today=late, types=invoices, statuses=frozenset({DisplayStatus.OVERDUE}))
    )
    assert [item.id for item in overdue.items] == [open_one]
    facets = handlers.facets(DocumentQuery(today=late, types=invoices))
    assert facets.status_counts == {DisplayStatus.WRITTEN_OFF: 1, DisplayStatus.OVERDUE: 1}
    [sums] = facets.totals
    assert (sums.count, sums.total, sums.open) == (2, chf("1697.50"), chf("38.00"))

    with SqlUnitOfWork(engine) as uow:
        [figures] = uow.documents.figures(late)
    # Written off is neither open nor received.
    assert (figures.open, figures.overdue, figures.paid) == (
        chf("38.00"),
        chf("38.00"),
        chf("1000.00"),
    )
    assert (figures.open_count, figures.overdue_count) == (1, 1)

    clock.set(LATER)
    handlers.add_payment(lost, PaymentInput(paid_on=LATER.date(), amount="659.50"))
    with SqlUnitOfWork(engine) as uow:
        [after] = uow.documents.figures(LATER.date())
        days = uow.documents.days_to_pay(date(2025, 1, 1))
    assert after.paid == chf("1659.50")
    # Paid in full, but after it was written off: no measure of how customers pay.
    assert handlers.get(lost).document.status is DocumentStatus.PAID
    assert days == []


def test_bad_debts(engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]) -> None:
    handlers, customer, clock = setup
    with SqlUnitOfWork(engine) as uow:
        assert uow.documents.bad_debts() == []
    old = issued(handlers, customer, issue_date=date(2025, 11, 20))
    handlers.add_payment(old, PaymentInput(paid_on=date(2025, 12, 1), amount="1000"))
    new = issued(handlers, customer, lines=(FOOD,))
    issued(handlers, customer)  # open: no bad debt
    handlers.write_off(new, GONE)
    handlers.write_off(
        old, WriteOffInput(written_off_on=date(2025, 12, 31), reason=WriteOffReason.TIME_BARRED)
    )
    clock.set(LATER)
    handlers.add_payment(old, PaymentInput(paid_on=date(2027, 1, 5), amount="100"))
    handlers.add_payment(old, PaymentInput(paid_on=date(2027, 2, 5), amount="50"))
    with SqlUnitOfWork(engine) as uow:
        debts = uow.documents.bad_debts()
    # In the order they are dated; payments from before the write-off are no recoveries.
    assert [
        (debt.write_off.written_off_on, debt.write_off.amount, debt.write_off.reason)
        for debt in debts
    ] == [
        (date(2025, 12, 31), chf("659.50"), WriteOffReason.TIME_BARRED),
        (TODAY, chf("38.00"), WriteOffReason.GONE),
    ]
    assert debts[0].recoveries == (
        (date(2027, 1, 5), chf("100.00")),
        (date(2027, 2, 5), chf("50.00")),
    )
    assert debts[1].recoveries == ()
    assert debts[0].totals == handlers.get(old).document.frozen_totals
    assert debts[0].write_off == handlers.get(old).document.write_off

    years = handlers.bad_debts()
    assert [(year.year, year.written_off, year.recovered, year.loss) for year in years] == [
        (2027, chf("0"), chf("150.00"), chf("-150.00")),
        (2026, chf("38.00"), chf("0"), chf("38.00")),
        (2025, chf("659.50"), chf("0"), chf("659.50")),
    ]
