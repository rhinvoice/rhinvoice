"""Tax rates owned by the company (ADR 0044).

A rate has a name, its category for the e-invoice and dated percentages: a change of the
percentage adds a value with the date it applies from, so documents keep the percentage of
their date of supply. Country presets (``rhinvoice.domain.country``) bring the legal rates;
users rename, hide or add rates.

No tax advice: rates are provided without warranty (see README).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.text import clean_text
from rhinvoice.domain.tax.category import TaxCategory

if TYPE_CHECKING:
    from datetime import date
    from uuid import UUID

MAX_RATE_NAME = 60
MAX_RATE_TEXT = 300
MAX_RATE_VALUES = 30
MAX_PERCENT = Decimal(100)
PERCENT_STEP = Decimal("0.01")
ZERO = Decimal(0)


class RateCategory(StrEnum):
    """The EN 16931 VAT category (UNCL5305) of a domestic taxable line with this rate."""

    STANDARD = "S"
    """Taxed at a rate above zero (standard, reduced and special rates, flat rates)."""
    ZERO = "Z"
    """Taxable at 0 %."""
    EXEMPT = "E"
    """Exempt from VAT; the invoice names the reason."""


_KINDS = {
    RateCategory.STANDARD: TaxCategory.STANDARD,
    RateCategory.ZERO: TaxCategory.ZERO,
    RateCategory.EXEMPT: TaxCategory.EXEMPT,
}


@dataclass(frozen=True, slots=True)
class RateValue:
    valid_from: date
    percent: Decimal

    def __post_init__(self) -> None:
        if not ZERO <= self.percent < MAX_PERCENT:
            raise ValidationError("percent", "the percentage must be from 0 to below 100")
        if self.percent != self.percent.quantize(PERCENT_STEP):
            raise ValidationError("percent", "the percentage has at most two decimal places")


@dataclass(frozen=True, slots=True)
class TaxRate:
    id: UUID
    name: str
    category: RateCategory
    values: tuple[RateValue, ...]
    """Oldest first; each value applies from its date until the next one."""
    exemption_reason: str = ""
    """Why the supply is exempt; required for category E (BR-E-10), printed with the line."""
    notice: str = ""
    """Printed on documents that use the rate, e.g. "Durchschnittssatz nach § 24 UStG"."""
    preset: str | None = None
    """The country preset the rate comes from; a release may add new values to it."""
    hidden: bool = False
    """Not offered for new lines; lines and articles that use it keep it."""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "name", clean_text(self.name, "name", max_length=MAX_RATE_NAME, required=True)
        )
        for field_name in ("exemption_reason", "notice"):
            object.__setattr__(
                self,
                field_name,
                clean_text(getattr(self, field_name), field_name, max_length=MAX_RATE_TEXT),
            )
        if not 1 <= len(self.values) <= MAX_RATE_VALUES:
            raise ValidationError(
                "values", f"a rate needs 1 to {MAX_RATE_VALUES} dated percentages"
            )
        dates = [value.valid_from for value in self.values]
        if dates != sorted(set(dates)):
            raise ValidationError("values", "the dates of the percentages must differ")
        self._check_category()

    def _check_category(self) -> None:
        """Enforce the EN 16931 rules on category and rate, so no e-invoice gets rejected."""
        if self.category is RateCategory.STANDARD:
            if any(value.percent == ZERO for value in self.values):
                raise ValidationError(
                    "category",
                    "a taxable rate (S) needs a percentage above 0",
                    code="rate_standard_needs_percent",
                )
            return
        if any(value.percent != ZERO for value in self.values):
            raise ValidationError(
                "category",
                "zero-rated (Z) and exempt (E) rates must be 0 %",
                code="rate_zero_needs_zero",
            )
        if self.category is RateCategory.EXEMPT and not self.exemption_reason:
            raise ValidationError(
                "exemption_reason",
                "an exempt rate (E) needs the reason for the exemption",
                code="rate_exempt_needs_reason",
            )

    @property
    def kind(self) -> TaxCategory:
        """The tax category of the lines with this rate."""
        return _KINDS[self.category]

    def frozen(self) -> FrozenRate:
        """Return what a document issued with this rate keeps of it."""
        return FrozenRate(
            id=self.id,
            name=self.name,
            category=self.category,
            notice=self.notice,
            exemption_reason=self.exemption_reason,
        )

    def percent_on(self, on: date) -> Decimal:
        """Return the percentage on the date of supply ``on``."""
        applying = [value for value in self.values if value.valid_from <= on]
        if not applying:
            raise ValidationError(
                "service_date",
                f"the rate {self.name!r} has no percentage before {self.values[0].valid_from}",
                code="rate_not_yet_valid",
            )
        return applying[-1].percent


def check_rate_choice(kind: TaxCategory, rate_id: UUID | None) -> None:
    """Check that a pass-through item names no rate.

    Other positions and articles without a rate take the company's default rate: articles
    and plans saved before the company had its rates (migration 0027) have none until the
    company is set up. Totals and issuing ask every taxed position for its rate.
    """
    if kind is TaxCategory.PASS_THROUGH and rate_id is not None:
        raise ValidationError("tax_rate_id", "a pass-through item has no tax rate")


@dataclass(frozen=True, slots=True)
class FrozenRate:
    """A rate as a document was issued with it: its words never change afterwards."""

    id: UUID
    name: str
    category: RateCategory
    notice: str = ""
    exemption_reason: str = ""
