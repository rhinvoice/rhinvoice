"""Dunning levels and reminders in PostgreSQL."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from rhinvoice.application.document.handlers import DocumentHandlers
from rhinvoice.application.dunning.handlers import DunningHandlers
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.dunning.reminder import DEFAULT_LEVELS
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.infrastructure.db.uow import SqlUnitOfWork
from tests.integration.test_document_persistence import TODAY, draft, factory, setup

__all__ = ["setup"]  # the fixture of the document tests


def test_levels_are_saved(engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]) -> None:
    documents, _, clock = setup
    dunning = DunningHandlers(uow=factory(engine), clock=clock, documents=documents)
    assert dunning.levels() == list(DEFAULT_LEVELS)
    changed = [
        replace(level, fee=Decimal("12.50"), text_en="Please pay.") for level in DEFAULT_LEVELS
    ]
    dunning.save_levels(changed)
    assert dunning.levels() == changed
    dunning.save_levels(list(DEFAULT_LEVELS))
    assert dunning.levels() == list(DEFAULT_LEVELS)


def test_reminders_are_saved_once_per_level(
    engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    documents, customer, clock = setup
    due = TODAY - timedelta(days=20)
    created = documents.create(
        DocumentType.INVOICE,
        draft(customer, issue_date=due - timedelta(days=30), due_date=due),
    ).document.id
    documents.issue(created)
    dunning = DunningHandlers(uow=factory(engine), clock=clock, documents=documents)
    first, _ = dunning.remind(created, level=1)
    second, _ = dunning.remind(created, level=2, early=True)
    assert dunning.reminders(created) == [first, second]
    assert dunning.get(first.id) == first
    [item] = dunning.overview()
    assert item.reminders == (first, second)
    with SqlUnitOfWork(engine) as uow:
        assert uow.dunning.get(new_id()) is None
        assert uow.dunning.reminders([]) == {}
        with pytest.raises(IntegrityError):
            uow.dunning.add(replace(first, id=new_id()))
