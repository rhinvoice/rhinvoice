"""The company's tax rates in PostgreSQL (ADR 0044)."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from rhinvoice.application.catalog.handlers import ArticleHandlers, SaveArticle
from rhinvoice.application.document.handlers import DocumentHandlers, DraftInput, LineInput
from rhinvoice.application.tax.handlers import TaxRateHandlers
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import LineKind
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.tax.presets import EXEMPT, REDUCED, STANDARD, ZERO
from rhinvoice.domain.tax.tax_rate import RateCategory, RateValue, TaxRate
from rhinvoice.infrastructure.db.uow import SqlUnitOfWork
from tests.integration.test_document_persistence import setup
from tests.integration.test_recurring_persistence import TEMPLATE, plan
from tests.unit.domain import factories

__all__ = ["setup"]  # the fixture of the document tests

AVERAGE = TaxRate(
    id=UUID(int=0x24),
    name="Landwirtschaft § 24",
    category=RateCategory.STANDARD,
    values=(RateValue(date(2025, 1, 1), Decimal("7.8")),),
    notice="Durchschnittssatz § 24 UStG",
    preset="de_24_other",
    hidden=True,
)


def test_rates_keep_their_order_and_values(engine: Engine) -> None:
    exempt = TaxRate(
        id=new_id(),
        name="Heilbehandlung",
        category=RateCategory.EXEMPT,
        values=(RateValue(date(2007, 1, 1), Decimal(0)),),
        exemption_reason="§ 4 Nr. 14 UStG",
    )
    with SqlUnitOfWork(engine) as uow:
        assert uow.tax_rates.list() == []
        uow.tax_rates.add(AVERAGE)
        uow.tax_rates.add(exempt)
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        assert uow.tax_rates.list(for_update=True) == [AVERAGE, exempt]
        renamed = replace(AVERAGE, name="Landwirtschaft", hidden=False)
        uow.tax_rates.update(renamed)
        uow.tax_rates.delete(exempt.id)
        uow.tax_rates.add(exempt)
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        # Added after the others.
        assert uow.tax_rates.list() == [renamed, exempt]
    with engine.connect() as connection:
        positions = connection.execute(text("SELECT position FROM tax_rates ORDER BY position"))
        assert list(positions.scalars()) == [0, 1]


def test_names_and_presets_are_unique(engine: Engine) -> None:
    with SqlUnitOfWork(engine) as uow:
        uow.tax_rates.add(AVERAGE)
        uow.commit()
    for twin in (
        replace(AVERAGE, id=new_id(), name="LANDWIRTSCHAFT § 24", preset=None),
        replace(AVERAGE, id=new_id(), name="Andere"),
    ):
        with SqlUnitOfWork(engine) as uow, pytest.raises(IntegrityError):
            uow.tax_rates.add(twin)


def test_rates_in_use_cannot_be_deleted(
    engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    documents, customer, clock = setup
    rates = TaxRateHandlers(uow=lambda: SqlUnitOfWork(engine))
    assert not any(view.in_use for view in rates.rates())
    hours = LineInput(kind=LineKind.ITEM, description="Beratung", unit_price="80")
    fee = replace(hours, pass_through=True)
    documents.create(DocumentType.INVOICE, DraftInput(customer_id=customer, lines=(hours, fee)))
    ArticleHandlers(uow=lambda: SqlUnitOfWork(engine), clock=clock).create(
        SaveArticle(name="Kurs", tax_rate_id=factories.rate_id(EXEMPT))
    )
    with SqlUnitOfWork(engine) as uow:
        uow.recurring.add(plan(customer, "Hosting", clock.today()))
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        # Documents, articles and the plan's template (REDUCED, as JSON).
        assert uow.tax_rates.used_ids() == {
            factories.rate_id(STANDARD),
            factories.rate_id(EXEMPT),
            factories.rate_id(REDUCED),
        }
    assert [view.in_use for view in rates.rates()] == [True, True, False, False, True]
    rates.delete(factories.rate_id(ZERO))
    # The database refuses what a caller should have checked.
    for used in (STANDARD, EXEMPT):
        with SqlUnitOfWork(engine) as uow, pytest.raises(IntegrityError):
            uow.tax_rates.delete(factories.rate_id(used))
    assert TEMPLATE.rate_ids == (factories.rate_id(REDUCED),)
