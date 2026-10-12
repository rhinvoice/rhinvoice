"""Payment reminders: which invoices are overdue, and writing the next reminder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rhinvoice.application.common import MAX_PAGE_SIZE, PageRequest, SortDirection
from rhinvoice.application.document.ports import DocumentQuery, DocumentSort
from rhinvoice.application.errors import NotFoundError
from rhinvoice.domain.document.document import DisplayStatus, DocumentType
from rhinvoice.domain.dunning.reminder import LEVELS, Dunning
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.identifier import new_id

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from rhinvoice.application.document.handlers import DocumentHandlers, DocumentView
    from rhinvoice.application.document.ports import DocumentSummary
    from rhinvoice.application.uow import UnitOfWorkFactory
    from rhinvoice.domain.dunning.reminder import DunningLevel, NextReminder, Reminder
    from rhinvoice.domain.shared.clock import Clock


@dataclass(frozen=True, slots=True)
class DunningItem:
    invoice: DocumentSummary
    reminders: tuple[Reminder, ...]
    next: NextReminder | None
    """None when all three reminders were written."""


@dataclass(frozen=True, slots=True)
class DunningHandlers:
    uow: UnitOfWorkFactory
    clock: Clock
    documents: DocumentHandlers

    def levels(self) -> list[DunningLevel]:
        with self.uow() as uow:
            return uow.dunning.levels()

    def save_levels(self, levels: Sequence[DunningLevel]) -> list[DunningLevel]:
        if sorted(level.level for level in levels) != list(LEVELS):
            raise ValidationError(
                "levels", "each of the three levels once", code="levels_incomplete"
            )
        ordered = sorted(levels, key=lambda level: level.level)
        with self.uow() as uow:
            uow.dunning.save_levels(ordered)
            uow.commit()
        return ordered

    def overview(self) -> list[DunningItem]:
        """List the overdue invoices, longest overdue first, with their reminders."""
        today = self.clock.today()
        summaries: list[DocumentSummary] = []
        with self.uow() as uow:
            while True:
                page = uow.documents.search(
                    DocumentQuery(
                        today=today,
                        types=frozenset({DocumentType.INVOICE}),
                        statuses=frozenset({DisplayStatus.OVERDUE}),
                        sort=DocumentSort.DUE_DATE,
                        direction=SortDirection.ASC,
                        page=PageRequest(limit=MAX_PAGE_SIZE, offset=len(summaries)),
                    )
                )
                summaries.extend(page.items)
                if len(summaries) >= page.total or not page.items:
                    break
            reminders = uow.dunning.reminders([summary.id for summary in summaries])
            levels = uow.dunning.levels()
            # Issued invoices are never deleted: each summary has its document.
            invoices = {
                summary.id: invoice
                for summary in summaries
                if (invoice := uow.documents.get(summary.id)) is not None
            }
        return [
            DunningItem(
                summary,
                tuple(reminders.get(summary.id, ())),
                Dunning(invoices[summary.id], reminders.get(summary.id, ())).next(levels, today),
            )
            for summary in summaries
        ]

    def reminders(self, invoice_id: UUID) -> list[Reminder]:
        with self.uow() as uow:
            if uow.documents.get(invoice_id) is None:
                raise NotFoundError("document not found")
            return uow.dunning.reminders([invoice_id]).get(invoice_id, [])

    def get(self, reminder_id: UUID) -> Reminder:
        with self.uow() as uow:
            reminder = uow.dunning.get(reminder_id)
        if reminder is None:
            raise NotFoundError("reminder not found")
        return reminder

    def remind(
        self, invoice_id: UUID, *, level: int, early: bool = False
    ) -> tuple[Reminder, DocumentView]:
        """Write the next reminder of an overdue invoice and note it in its history.

        ``level`` is the level the person saw: a second click writes nothing more.
        """
        with self.uow() as uow:
            invoice = uow.documents.get(invoice_id, for_update=True)
            if invoice is None:
                raise NotFoundError("document not found")
            written = uow.dunning.reminders([invoice_id]).get(invoice_id, [])
            reminder = Dunning(invoice, written).remind(
                uow.dunning.levels(),
                level=level,
                early=early,
                reminder_id=new_id(),
                today=self.clock.today(),
                now=self.clock.now(),
            )
            uow.dunning.add(reminder)
            view = self.documents.save_in(
                uow, invoice.record_reminder(reminder.level, self.clock.now())
            )
            uow.commit()
        return reminder, view
