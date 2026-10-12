"""Money value object based on :class:`decimal.Decimal`.

Amounts keep full precision during calculations. Rounding happens explicitly
(see :meth:`Money.round_to_minor` and :meth:`Money.round_to_step`), which lets
the document calculation round only the final amount.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from enum import StrEnum
from typing import Self

from rhinvoice.domain.shared.errors import CurrencyMismatchError, ValidationError


class Currency(StrEnum):
    CHF = "CHF"
    EUR = "EUR"

    @property
    def minor_units(self) -> int:
        return 2

    @property
    def minor_step(self) -> Decimal:
        return Decimal(1).scaleb(-self.minor_units)


def parse_decimal(value: str | int | Decimal, field: str) -> Decimal:
    """Parse user input into a finite decimal or raise a ValidationError."""
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValidationError(field, f"'{value}' is not a valid number") from None
    if not result.is_finite():
        raise ValidationError(field, f"'{value}' is not a valid number")
    return result


CALCULATION_PRECISION = 60
"""Significant digits for intermediate results; far beyond any invoice amount."""


def round_half_up(value: Decimal, step: Decimal) -> Decimal:
    """Commercial rounding of ``value`` to a multiple of ``step`` (half away from zero)."""
    if step <= 0:
        raise ValidationError("step", "rounding step must be positive")
    with localcontext() as context:
        context.prec = CALCULATION_PRECISION
        units = (value / step).to_integral_value(rounding=ROUND_HALF_UP)
        return (units * step).quantize(step)


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        if not self.amount.is_finite():
            raise ValidationError("amount", "amount must be finite")

    @classmethod
    def zero(cls, currency: Currency) -> Self:
        return cls(Decimal(0), currency)

    @classmethod
    def of(cls, amount: str | int | Decimal, currency: Currency) -> Self:
        return cls(parse_decimal(amount, "amount"), currency)

    @classmethod
    def from_minor(cls, minor: int, currency: Currency) -> Self:
        return cls(Decimal(minor).scaleb(-currency.minor_units), currency)

    def to_minor(self) -> int:
        """Return the amount rounded (half away from zero) to minor units, e.g. cents."""
        rounded = self.round_to_minor()
        return int(rounded.amount.scaleb(self.currency.minor_units))

    def _check(self, other: Money) -> None:
        if other.currency is not self.currency:
            raise CurrencyMismatchError(
                f"cannot combine {self.currency} with {other.currency}",
            )

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: Decimal | int) -> Money:
        return Money(self.amount * factor, self.currency)

    __rmul__ = __mul__

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    def __lt__(self, other: Money) -> bool:
        self._check(other)
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._check(other)
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        self._check(other)
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        self._check(other)
        return self.amount >= other.amount

    @property
    def is_zero(self) -> bool:
        return self.amount == 0

    @property
    def is_negative(self) -> bool:
        return self.amount < 0

    def round_to_minor(self) -> Money:
        return self.round_to_step(self.currency.minor_step)

    def round_to_step(self, step: Decimal) -> Money:
        return Money(round_half_up(self.amount, step), self.currency)

    def percent(self, rate: Decimal) -> Money:
        """Return ``rate`` percent of this amount without rounding."""
        return Money(self.amount * rate / Decimal(100), self.currency)

    def __str__(self) -> str:
        return f"{self.currency} {self.round_to_minor().amount}"
