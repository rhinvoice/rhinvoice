"""Where plans and their runs are kept."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Collection
    from datetime import date
    from uuid import UUID

    from rhinvoice.domain.recurring.plan import PlanRun, RecurringPlan


class RecurringRepository(Protocol):
    def all(self) -> list[RecurringPlan]:
        """All plans, by name."""
        ...

    def get(self, plan_id: UUID, *, for_update: bool = False) -> RecurringPlan | None: ...
    def add(self, plan: RecurringPlan) -> None: ...
    def update(self, plan: RecurringPlan) -> None: ...
    def delete(self, plan_id: UUID) -> None:
        """Remove the plan and its runs; the invoices it wrote stay."""
        ...

    def due(self, today: date) -> list[UUID]:
        """Return the active plans whose next invoice is due."""
        ...

    def claim(self, run: PlanRun) -> bool:
        """Record that a period is being written; False when it already was (once only)."""
        ...

    def finish(self, run: PlanRun) -> None:
        """Store the result of a claimed run."""
        ...

    def runs(self, plan_ids: Collection[UUID], *, limit: int) -> dict[UUID, list[PlanRun]]:
        """Return the latest runs of the plans, newest first, at most ``limit`` each."""
        ...
