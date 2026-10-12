"""Dunning levels and the reminders written for invoices."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, insert, select

from rhinvoice.domain.dunning.reminder import DEFAULT_LEVELS, DunningLevel, Reminder
from rhinvoice.domain.shared.money import Currency, Money
from rhinvoice.infrastructure.db.tables import dunning_levels, reminders

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence
    from uuid import UUID

    from sqlalchemy import Connection, RowMapping


def _reminder_from_row(row: RowMapping) -> Reminder:
    currency = Currency(row["currency"])
    return Reminder(
        id=row["id"],
        invoice_id=row["invoice_id"],
        level=row["level"],
        issued_on=row["issued_on"],
        due_date=row["due_date"],
        open_amount=Money(row["open_amount"], currency),
        fee=Money(row["fee"], currency),
        created_at=row["created_at"],
        text=row["text"],
    )


class SqlDunningRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def levels(self) -> list[DunningLevel]:
        rows = self._connection.execute(
            select(dunning_levels).order_by(dunning_levels.c.level)
        ).mappings()
        saved = [
            DunningLevel(
                level=row["level"],
                days_after_due=row["days_after_due"],
                payment_days=row["payment_days"],
                fee=row["fee"],
                text_de=row["text_de"],
                text_en=row["text_en"],
            )
            for row in rows
        ]
        return saved or list(DEFAULT_LEVELS)

    def save_levels(self, levels: Sequence[DunningLevel]) -> None:
        self._connection.execute(delete(dunning_levels))
        self._connection.execute(
            insert(dunning_levels),
            [
                {
                    "level": level.level,
                    "days_after_due": level.days_after_due,
                    "payment_days": level.payment_days,
                    "fee": level.fee,
                    "text_de": level.text_de,
                    "text_en": level.text_en,
                }
                for level in levels
            ],
        )

    def reminders(self, invoice_ids: Collection[UUID]) -> dict[UUID, list[Reminder]]:
        found: dict[UUID, list[Reminder]] = {}
        if not invoice_ids:
            return found
        rows = self._connection.execute(
            select(reminders)
            .where(reminders.c.invoice_id.in_(list(invoice_ids)))
            .order_by(reminders.c.level)
        ).mappings()
        for row in rows:
            found.setdefault(row["invoice_id"], []).append(_reminder_from_row(row))
        return found

    def get(self, reminder_id: UUID) -> Reminder | None:
        row = (
            self._connection.execute(select(reminders).where(reminders.c.id == reminder_id))
            .mappings()
            .first()
        )
        return None if row is None else _reminder_from_row(row)

    def add(self, reminder: Reminder) -> None:
        self._connection.execute(
            insert(reminders).values(
                id=reminder.id,
                invoice_id=reminder.invoice_id,
                level=reminder.level,
                issued_on=reminder.issued_on,
                due_date=reminder.due_date,
                currency=reminder.open_amount.currency.value,
                open_amount=reminder.open_amount.amount,
                fee=reminder.fee.amount,
                created_at=reminder.created_at,
                text=reminder.text,
            )
        )
