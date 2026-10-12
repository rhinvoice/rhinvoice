"""Dated VAT rate sets. The rate on the date of supply applies.

The rates of each country live in its profile (``rhinvoice.domain.country``), with
their official sources.

No tax advice: rates are provided without warranty (see README).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.tax.category import TaxCategory

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date

ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class TaxRateSet:
    valid_from: date
    valid_to: date | None
    """Inclusive end date; None means "until further notice"."""
    standard: Decimal
    reduced: Decimal
    special: Decimal | None
    """A third rate (CH/LI accommodation, AT 13 %); None where the country has none."""

    def applies_on(self, on: date) -> bool:
        return self.valid_from <= on and (self.valid_to is None or on <= self.valid_to)

    def rate(self, category: TaxCategory) -> Decimal:
        if category is TaxCategory.STANDARD:
            return self.standard
        if category is TaxCategory.REDUCED:
            return self.reduced
        if category is TaxCategory.SPECIAL:
            if self.special is None:
                raise ValidationError("tax_category", "this tax rate does not exist in the country")
            return self.special
        return ZERO


def rate_set_on(rate_sets: Sequence[TaxRateSet], on: date) -> TaxRateSet:
    """Return the rate set that applies on ``on``."""
    for rate_set in rate_sets:
        if rate_set.applies_on(on):
            return rate_set
    raise ValidationError("service_date", f"no VAT rates known on {on.isoformat()}")
