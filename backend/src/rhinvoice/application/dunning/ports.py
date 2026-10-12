"""Dunning levels and the reminders written for invoices."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence
    from uuid import UUID

    from rhinvoice.domain.dunning.reminder import DunningLevel, Reminder


class DunningRepository(Protocol):
    def levels(self) -> list[DunningLevel]:
        """Return the three levels, by level."""
        ...

    def save_levels(self, levels: Sequence[DunningLevel]) -> None: ...
    def reminders(self, invoice_ids: Collection[UUID]) -> dict[UUID, list[Reminder]]:
        """Return the reminders of these invoices, oldest first (invoices without: absent)."""
        ...

    def get(self, reminder_id: UUID) -> Reminder | None: ...
    def add(self, reminder: Reminder) -> None: ...
