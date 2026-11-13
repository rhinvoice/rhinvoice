from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from uuid import UUID

    from rhinvoice.domain.tax.tax_rate import TaxRate


class TaxRateRepository(Protocol):
    def list(self, *, for_update: bool = False) -> list[TaxRate]:
        """Return every rate of the company in its order (presets first, as seeded).

        ``for_update`` locks them until the commit, so that changes run one after the other
        and names stay unique.
        """
        ...

    def add(self, rate: TaxRate) -> None:
        """Add a rate after the others."""
        ...

    def update(self, rate: TaxRate) -> None: ...
    def delete(self, rate_id: UUID) -> None: ...
    def used_ids(self) -> frozenset[UUID]:
        """Return the rates that document lines, articles or recurring plans refer to."""
        ...
