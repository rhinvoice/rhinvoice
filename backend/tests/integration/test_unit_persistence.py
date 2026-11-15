"""The company's units in PostgreSQL (ADR 0046)."""

from dataclasses import replace
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from rhinvoice.application.catalog.handlers import ArticleHandlers, SaveArticle
from rhinvoice.application.catalog.units import Removal, UnitHandlers
from rhinvoice.application.document.handlers import DocumentHandlers, DraftInput, LineInput
from rhinvoice.domain.catalog.unit import LineUnit, Unit
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import LineKind
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.infrastructure.db.repositories.units import SqlUnitRepository
from rhinvoice.infrastructure.db.uow import SqlUnitOfWork
from tests.integration.test_document_persistence import setup
from tests.integration.test_recurring_persistence import plan
from tests.unit.domain import factories

__all__ = ["setup"]  # the fixture of the document tests

START = list(factories.units().values())
QUINTAL = Unit(
    id=UUID(int=0xDA),
    code="DTN",
    label="dz",
    label_en="dt",
    label_it="q",
    description="Doppelzentner (100 kg)",
    preset="DTN",
    hidden=True,
)


def test_units_keep_their_order_and_labels(engine: Engine) -> None:
    with SqlUnitOfWork(engine) as uow:
        assert uow.units.list() == START
        uow.units.add(QUINTAL)
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        assert uow.units.list(for_update=True) == [*START, QUINTAL]
        shown = replace(QUINTAL, label="Dz.", label_en="", hidden=False)
        uow.units.update(shown)
        uow.units.reorder([QUINTAL.id, *(unit.id for unit in reversed(START))])
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        assert uow.units.list() == [shown, *reversed(START)]
        assert uow.units.delete(START[0].id) is True
        uow.units.add(START[0])
        uow.units.reorder([])
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        # Added after the others.
        assert uow.units.list()[-1] == START[0]
    with engine.connect() as connection:
        labels = connection.execute(text("SELECT labels FROM units WHERE code = 'DTN'"))
        assert labels.scalar_one() == {"it": "q"}


def test_labels_and_presets_are_unique(engine: Engine) -> None:
    for twin in (
        replace(QUINTAL, id=new_id(), label="STK.", preset=None),
        replace(QUINTAL, id=new_id(), label="Anderes", preset="C62"),
    ):
        with SqlUnitOfWork(engine) as uow, pytest.raises(IntegrityError):
            uow.units.add(twin)


def test_units_in_use_are_hidden_not_deleted(
    engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    documents, customer, clock = setup
    units = UnitHandlers(uow=lambda: SqlUnitOfWork(engine))
    assert not any(view.in_use for view in units.units())
    hours = LineInput(
        kind=LineKind.ITEM,
        description="Beratung",
        unit_price="80",
        unit_id=factories.unit_id("HUR"),
    )
    documents.create(DocumentType.INVOICE, DraftInput(customer_id=customer, lines=(hours,)))
    ArticleHandlers(uow=lambda: SqlUnitOfWork(engine), clock=clock).create(
        SaveArticle(name="Kabel")
    )
    with SqlUnitOfWork(engine) as uow:
        uow.recurring.add(plan(customer, "Hosting", clock.today()))
        uow.commit()
    used = {factories.unit_id(code) for code in ("HUR", "C62", "MON")}
    with SqlUnitOfWork(engine) as uow:
        # Documents, articles and the plan's template (MON, as JSON).
        assert uow.units.used_ids() == used
    assert {view.unit.id for view in units.units() if view.in_use} == used
    assert units.remove(factories.unit_id("HUR")) is Removal.HIDDEN
    assert units.remove(factories.unit_id("MIN")) is Removal.DELETED
    # The foreign keys refuse what a caller should have checked; the transaction goes on.
    for code in ("HUR", "C62"):
        with SqlUnitOfWork(engine) as uow:
            assert uow.units.delete(factories.unit_id(code)) is False
            assert factories.unit_id(code) in {unit.id for unit in uow.units.list()}
            uow.commit()


def test_a_unit_used_meanwhile_is_hidden_not_deleted(
    engine: Engine,
    setup: tuple[DocumentHandlers, UUID, FixedClock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A line saved while the unit is removed: its foreign key refuses the delete."""
    documents, customer, clock = setup
    hours, pieces = factories.unit_id("HUR"), factories.unit_id("C62")
    line = LineInput(kind=LineKind.ITEM, description="Beratung", unit_price="80", unit_id=hours)
    documents.create(DocumentType.INVOICE, DraftInput(customer_id=customer, lines=(line,)))
    ArticleHandlers(uow=lambda: SqlUnitOfWork(engine), clock=clock).create(
        SaveArticle(name="Kabel", unit_id=pieces)
    )

    # The draft and the article came after the remove looked for references.
    def no_references(_self: SqlUnitRepository) -> frozenset[UUID]:
        return frozenset()

    monkeypatch.setattr(SqlUnitRepository, "used_ids", no_references)
    units = UnitHandlers(uow=lambda: SqlUnitOfWork(engine))
    assert units.remove(hours) is Removal.HIDDEN
    assert units.remove(pieces) is Removal.HIDDEN
    assert units.remove(factories.unit_id("MIN")) is Removal.DELETED
    with SqlUnitOfWork(engine) as uow:
        stored = {unit.id: unit for unit in uow.units.list()}
    assert (stored[hours].hidden, stored[pieces].hidden) == (True, True)
    assert factories.unit_id("MIN") not in stored


def test_issued_lines_keep_their_unit(
    engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    documents, customer, _ = setup
    hours = factories.unit_id("HUR")
    line = LineInput(kind=LineKind.ITEM, description="Beratung", unit_price="80", unit_id=hours)
    loose = replace(line, unit_id=None)
    draft = documents.create(
        DocumentType.INVOICE, DraftInput(customer_id=customer, lines=(line, loose))
    )
    with engine.connect() as connection:
        stored = connection.execute(
            text("SELECT unit_id, unit_code, unit_label FROM document_lines ORDER BY position")
        ).all()
        assert [tuple(row) for row in stored] == [(hours, None, None), (None, None, None)]
    issued = documents.issue(draft.document.id)
    units = UnitHandlers(uow=lambda: SqlUnitOfWork(engine))
    renamed = units.units()[1].unit
    with SqlUnitOfWork(engine) as uow:
        uow.units.update(replace(renamed, label="Stunde"))
        uow.commit()
    again = documents.get(issued.document.id)
    assert [line.unit for line in again.document.content.lines] == [
        LineUnit("HUR", "Std."),
        None,
    ]
    # The database keeps a frozen unit whole.
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL session_replication_role = replica"))
        with pytest.raises(IntegrityError):
            connection.execute(text("UPDATE document_lines SET unit_label = NULL"))
