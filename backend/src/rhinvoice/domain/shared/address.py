"""Postal address.

Structured according to the Swiss QR-bill (Implementation Guidelines v2.3:
only structured addresses since November 2025) so that it can be printed on
the payment part without conversion. Field lengths follow those guidelines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.text import clean_text

if TYPE_CHECKING:
    from rhinvoice.domain.shared.country import CountryCode

MAX_STREET = 70
MAX_HOUSE_NUMBER = 16
MAX_SUPPLEMENT = 70
MAX_POSTAL_CODE = 16
MAX_CITY = 35


@dataclass(frozen=True, slots=True)
class Address:
    postal_code: str
    city: str
    country: CountryCode
    street: str = ""
    house_number: str = ""
    supplement: str = ""
    """Additional line such as "c/o", "Postfach 12" or a department."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "street", clean_text(self.street, "street", max_length=MAX_STREET))
        object.__setattr__(
            self,
            "house_number",
            clean_text(self.house_number, "house_number", max_length=MAX_HOUSE_NUMBER),
        )
        object.__setattr__(
            self,
            "supplement",
            clean_text(self.supplement, "supplement", max_length=MAX_SUPPLEMENT),
        )
        object.__setattr__(
            self,
            "postal_code",
            clean_text(self.postal_code, "postal_code", max_length=MAX_POSTAL_CODE, required=True),
        )
        object.__setattr__(
            self,
            "city",
            clean_text(self.city, "city", max_length=MAX_CITY, required=True),
        )

    @property
    def street_line(self) -> str:
        return " ".join(part for part in (self.street, self.house_number) if part)

    def lines(self) -> list[str]:
        """Printable lines below the recipient name (without the country)."""
        return [
            line
            for line in (self.supplement, self.street_line, f"{self.postal_code} {self.city}")
            if line
        ]
