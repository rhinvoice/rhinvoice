"""Building blocks shared by several use cases."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from rhinvoice.domain.shared.address import Address
from rhinvoice.domain.shared.country import CountryCode
from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.tax.vat_number import VatNumber

MAX_PAGE_SIZE = 200


@dataclass(frozen=True, slots=True)
class AddressInput:
    postal_code: str
    city: str
    country: str
    street: str = ""
    house_number: str = ""
    supplement: str = ""

    def to_domain(self) -> Address:
        return Address(
            postal_code=self.postal_code,
            city=self.city,
            country=CountryCode(self.country.strip().upper()),
            street=self.street,
            house_number=self.house_number,
            supplement=self.supplement,
        )


def optional_email(raw: str | None) -> EmailAddress | None:
    return None if raw is None or not raw.strip() else EmailAddress.parse(raw)


def optional_vat_number(raw: str | None) -> VatNumber | None:
    return None if raw is None or not raw.strip() else VatNumber.parse(raw)


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


@dataclass(frozen=True, slots=True)
class PageRequest:
    limit: int = 50
    offset: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= MAX_PAGE_SIZE:
            raise ValidationError("limit", f"limit must be between 1 and {MAX_PAGE_SIZE}")
        if self.offset < 0:
            raise ValidationError("offset", "offset must not be negative")


@dataclass(frozen=True, slots=True)
class Page[T]:
    items: list[T]
    total: int
