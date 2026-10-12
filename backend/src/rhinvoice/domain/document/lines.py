"""Document lines and discounts."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.text import clean_multiline, clean_text
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply

if TYPE_CHECKING:
    from uuid import UUID

    from rhinvoice.domain.catalog.unit import Unit

MAX_DESCRIPTION = 500
MAX_DETAILS = 4000
MAX_QUANTITY = Decimal(999999999)
MAX_UNIT_PRICE = Decimal("99999999.9999")
QUANTITY_STEP = Decimal("0.0001")
PRICE_STEP = Decimal("0.0001")
PERCENT_STEP = Decimal("0.01")
HUNDRED = Decimal(100)


class LineKind(StrEnum):
    ITEM = "item"
    TEXT = "text"
    """A heading or free text without amount."""


class PriceMode(StrEnum):
    NET = "net"
    """Unit prices exclude VAT (B2B)."""
    GROSS = "gross"
    """Unit prices include VAT (B2C)."""


def _precise(value: Decimal, step: Decimal, field_name: str, label: str) -> None:
    if value != value.quantize(step):
        raise ValidationError(field_name, f"{label} has too many decimal places")


@dataclass(frozen=True, slots=True)
class DocumentLine:
    id: UUID
    kind: LineKind
    description: str
    details: str = ""
    quantity: Decimal = Decimal(1)
    unit: Unit | None = None
    unit_price: Decimal = Decimal(0)
    discount_percent: Decimal = Decimal(0)
    tax_category: TaxCategory = TaxCategory.STANDARD
    supply: Supply = Supply.SERVICE
    article_id: UUID | None = None
    tax_rate: Decimal | None = field(default=None)
    """VAT rate frozen when the document is issued (None while it is a draft)."""

    def __post_init__(self) -> None:
        required = self.kind is LineKind.ITEM
        object.__setattr__(
            self,
            "description",
            clean_text(
                self.description, "description", max_length=MAX_DESCRIPTION, required=required
            ),
        )
        object.__setattr__(
            self, "details", clean_multiline(self.details, "details", max_length=MAX_DETAILS)
        )
        if self.kind is LineKind.TEXT:
            if not (self.description or self.details):
                raise ValidationError("description", "a text line needs a text")
            return
        if abs(self.quantity) > MAX_QUANTITY:
            raise ValidationError("quantity", "quantity is too large")
        _precise(self.quantity, QUANTITY_STEP, "quantity", "quantity")
        if self.unit_price < 0 or self.unit_price > MAX_UNIT_PRICE:
            raise ValidationError(
                "unit_price", f"unit price must be between 0 and {MAX_UNIT_PRICE}"
            )
        _precise(self.unit_price, PRICE_STEP, "unit_price", "unit price")
        if not Decimal(0) <= self.discount_percent <= HUNDRED:
            raise ValidationError("discount_percent", "discount must be between 0 and 100 percent")
        _precise(self.discount_percent, PERCENT_STEP, "discount_percent", "discount")

    @property
    def is_item(self) -> bool:
        return self.kind is LineKind.ITEM

    def raw_amount(self) -> Decimal:
        """Quantity x unit price minus line discount, unrounded."""
        return self.quantity * self.unit_price * (HUNDRED - self.discount_percent) / HUNDRED


class DiscountKind(StrEnum):
    PERCENT = "percent"
    AMOUNT = "amount"


@dataclass(frozen=True, slots=True)
class Discount:
    kind: DiscountKind
    value: Decimal

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValidationError("discount", "discount must not be negative")
        if self.kind is DiscountKind.PERCENT:
            if self.value > HUNDRED:
                raise ValidationError("discount", "discount must be between 0 and 100 percent")
            _precise(self.value, PERCENT_STEP, "discount", "discount")
        else:
            _precise(self.value, PERCENT_STEP, "discount", "discount")

    @classmethod
    def none(cls) -> Discount:
        return cls(DiscountKind.PERCENT, Decimal(0))

    @property
    def is_zero(self) -> bool:
        return self.value == 0
