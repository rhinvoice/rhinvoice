"""Articles and services that can be added to documents."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.text import clean_multiline, clean_text
from rhinvoice.domain.tax.supply import Supply

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime
    from uuid import UUID

    from rhinvoice.domain.catalog.unit import Unit
    from rhinvoice.domain.shared.money import Currency
    from rhinvoice.domain.tax.category import TaxCategory

MAX_NUMBER = 30
MAX_NAME = 120
MAX_DESCRIPTION = 4000
MAX_GROUP = 50
PRICE_DECIMALS = 4
MAX_PRICE = Decimal("99999999.9999")
PRICE_STEP = Decimal(1).scaleb(-PRICE_DECIMALS)


@dataclass(frozen=True, slots=True)
class Article:
    id: UUID
    number: str
    name: str
    unit: Unit
    tax_category: TaxCategory
    prices: Mapping[Currency, Decimal]
    """Net unit price per currency (up to four decimal places)."""
    created_at: datetime
    description: str = ""
    group: str = ""
    archived: bool = False
    supply: Supply = Supply.SERVICE

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "number", clean_text(self.number, "number", max_length=MAX_NUMBER, required=True)
        )
        object.__setattr__(
            self, "name", clean_text(self.name, "name", max_length=MAX_NAME, required=True)
        )
        object.__setattr__(
            self,
            "description",
            clean_multiline(self.description, "description", max_length=MAX_DESCRIPTION),
        )
        object.__setattr__(self, "group", clean_text(self.group, "group", max_length=MAX_GROUP))
        for currency, price in self.prices.items():
            if price < 0 or price > MAX_PRICE:
                raise ValidationError(
                    f"prices.{currency}",
                    f"price must be between 0 and {MAX_PRICE}",
                )
            if price != price.quantize(PRICE_STEP):
                raise ValidationError(
                    f"prices.{currency}",
                    f"price must have at most {PRICE_DECIMALS} decimal places",
                )
        object.__setattr__(self, "prices", dict(self.prices))

    def price(self, currency: Currency) -> Decimal | None:
        return self.prices.get(currency)

    def archive(self) -> Article:
        return replace(self, archived=True)

    def restore(self) -> Article:
        return replace(self, archived=False)
