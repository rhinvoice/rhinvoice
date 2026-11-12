"""Where plans and their runs are kept."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping
    from datetime import date
    from uuid import UUID

    from rhinvoice.domain.recurring.plan import PlanRun, RecurringPlan
    from rhinvoice.domain.tax.tax_rate import TaxRate


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

    def adopt_rates(self, rates: Mapping[str, TaxRate]) -> None:
        """Give the lines of plans saved before the company had rates the rate of their category.

        ``rates`` names the rate of each former category as stored (standard, reduced,
        special, zero, exempt); pass-through items stay without (migration 0027).
        """
        ...
