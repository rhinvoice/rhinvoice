"""Recurring plans and their runs in PostgreSQL."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine

from rhinvoice.application.document.handlers import DocumentHandlers, DraftInput, LineInput
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import Discount, DiscountKind, LineKind, PriceMode
from rhinvoice.domain.recurring.plan import (
    Interval,
    InvoiceTemplate,
    PlanAction,
    PlanRun,
    RecurringPlan,
    RunOutcome,
)
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply
from rhinvoice.infrastructure.db.uow import SqlUnitOfWork
from tests.integration.test_document_persistence import NOW, TODAY, setup

__all__ = ["setup"]  # the fixture of the document tests

TEMPLATE = InvoiceTemplate(
    currency=Currency.EUR,
    price_mode=PriceMode.GROSS,
    lines=(
        LineInput(kind=LineKind.TEXT, description="Monat", details="laufend").to_domain(0),
        LineInput(
            kind=LineKind.ITEM,
            description="Server",
            quantity="1.5",
            unit="MON",
            unit_price="29.9",
            discount_percent="10",
            tax_category=TaxCategory.REDUCED,
            supply=Supply.GOODS,
        ).to_domain(1),
    ),
    language=Language.EN,
    discount=Discount(DiscountKind.AMOUNT, Decimal(5)),
    subject="Hosting",
    reference="K-1",
    intro_text="Hallo",
    payment_text="Zahlbar",
    closing_text="Danke",
)


def plan(customer: UUID, name: str, start: date) -> RecurringPlan:
    return RecurringPlan.new(
        UUID(int=hash(name) & 0xFFFF),
        name=name,
        customer_id=customer,
        interval=Interval.QUARTERLY,
        start_date=start,
        action=PlanAction.SEND,
        template=TEMPLATE,
        today=TODAY,
        now=NOW,
        end_date=start + timedelta(days=400),
        service_period=False,
    )


def test_plans_round_trip(engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]) -> None:
    _, customer, _ = setup
    first = plan(customer, "Wartung", TODAY)
    later = plan(customer, "Domain", TODAY + timedelta(days=10))
    with SqlUnitOfWork(engine) as uow:
        uow.recurring.add(first)
        uow.recurring.add(later)
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        assert uow.recurring.all() == [later, first]
        assert uow.recurring.get(first.id, for_update=True) == first
        assert uow.recurring.due(TODAY) == [first.id]
        assert uow.recurring.due(TODAY + timedelta(days=10)) == [first.id, later.id]
        uow.recurring.update(first.pause())
        uow.recurring.update(later.advance().advance().advance().advance().advance())
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        # Paused, and past its end.
        assert uow.recurring.due(date(2030, 1, 1)) == []
        nameless = replace(first, template=replace(TEMPLATE, language=None, discount=None))
        uow.recurring.update(nameless)
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        assert uow.recurring.get(first.id) == nameless
        uow.recurring.delete(first.id)
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        assert uow.recurring.get(first.id) is None


def test_each_period_is_claimed_once(
    engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    documents, customer, _ = setup
    monthly = plan(customer, "Hosting", TODAY)
    run = PlanRun(monthly.id, TODAY, NOW, RunOutcome.FAILED, code="interrupted")
    with SqlUnitOfWork(engine) as uow:
        uow.recurring.add(monthly)
        assert uow.recurring.runs([monthly.id], limit=5) == {}
        assert uow.recurring.claim(run)
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        assert not uow.recurring.claim(replace(run, outcome=RunOutcome.DRAFT))
        invoice = documents.create(
            DocumentType.INVOICE,
            DraftInput(
                customer_id=customer,
                lines=(LineInput(kind=LineKind.ITEM, description="x", unit_price="1"),),
            ),
        ).document.id
        done = replace(
            run, outcome=RunOutcome.SENT, document_id=invoice, code="", message="x" * 600
        )
        uow.recurring.finish(done)
        for months in (3, 6):
            uow.recurring.claim(replace(run, period_start=TODAY + timedelta(days=30 * months)))
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        runs = uow.recurring.runs([monthly.id], limit=2)[monthly.id]
        assert [found.period_start for found in runs] == [
            TODAY + timedelta(days=180),
            TODAY + timedelta(days=90),
        ]
        [oldest] = [
            found
            for found in uow.recurring.runs([monthly.id], limit=5)[monthly.id]
            if found.period_start == TODAY
        ]
        assert oldest == replace(done, message="x" * 500)
        assert uow.recurring.runs([], limit=5) == {}
