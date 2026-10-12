"""Shared API schemas."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, JsonValue

from rhinvoice.application.common import MAX_PAGE_SIZE, AddressInput, PageRequest, SortDirection
from rhinvoice.domain.catalog.unit import UNITS
from rhinvoice.domain.shared.country import ISO_3166_ALPHA2

if TYPE_CHECKING:
    from rhinvoice.domain.shared.address import Address

# At least one character that Python's str.strip() keeps. ECMAScript's "\s" does
# not cover U+001C-U+001F and U+0085, so they are listed explicitly.
NOT_BLANK_PATTERN = r"[^\s\x1c-\x1f\x85]"


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ErrorBody(ApiModel):
    code: str
    message: str
    details: dict[str, str]


class ErrorResponse(ApiModel):
    error: ErrorBody


ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 409, 422)
}


# --- Reusable field types mirroring the domain rules -------------------------------

ISO_COUNTRY_CODES: list[str] = sorted(ISO_3166_ALPHA2)
_COUNTRY_ENUM: list[JsonValue] = [*ISO_COUNTRY_CODES]
UNIT_CODES: list[JsonValue] = [*sorted(UNITS)]


def _known_country(value: str) -> str:
    if value not in ISO_3166_ALPHA2:
        msg = f"'{value}' is not an ISO 3166 country code"
        raise ValueError(msg)
    return value


CountryField = Annotated[
    str,
    AfterValidator(_known_country),
    Field(json_schema_extra={"enum": _COUNTRY_ENUM}),
]
DECIMAL_PATTERN = r"^\d{1,8}(\.\d{1,4})?$"
PERCENT_PATTERN = r"^(100(\.0{1,2})?|\d{1,2}(\.\d{1,2})?)$"


def text(max_length: int, *, required: bool = False) -> Any:  # noqa: ANN401 - pydantic FieldInfo
    """Declare a string field; required ones must contain a non-blank character."""
    if required:
        return Field(max_length=max_length, pattern=NOT_BLANK_PATTERN)
    return Field(default="", max_length=max_length)


class AddressFields(ApiModel):
    """Address lines without the country (which differs per use)."""

    street: str = text(70)
    house_number: str = text(16)
    supplement: str = text(70)
    postal_code: str = text(16, required=True)
    city: str = text(35, required=True)

    def to_input_with(self, country: str) -> AddressInput:
        return AddressInput(
            postal_code=self.postal_code,
            city=self.city,
            country=country,
            street=self.street,
            house_number=self.house_number,
            supplement=self.supplement,
        )


class AddressSchema(AddressFields):
    country: CountryField

    def to_input(self) -> AddressInput:
        return self.to_input_with(self.country)

    @classmethod
    def of(cls, address: Address) -> AddressSchema:
        return cls(
            street=address.street,
            house_number=address.house_number,
            supplement=address.supplement,
            postal_code=address.postal_code,
            city=address.city,
            country=address.country.value,
        )


class PageMeta(ApiModel):
    total: int
    limit: int
    offset: int


def price_text(value: Decimal) -> str:
    """Render a price with two to four decimals, e.g. "150.00" or "12.3456"."""
    two = value.quantize(Decimal("0.01"))
    return str(two) if two == value else str(value.normalize())


def plain_number(value: Decimal) -> str:
    """Render without trailing zeros or exponent, e.g. "2.5" or "10"."""
    return f"{value.normalize():f}"


class ListParams(ApiModel):
    """Common query parameters of list endpoints."""

    q: str = Field(default="", max_length=100)
    direction: SortDirection = SortDirection.ASC
    limit: int = Field(default=50, ge=1, le=MAX_PAGE_SIZE)
    offset: int = Field(default=0, ge=0, le=1_000_000)

    def page_request(self) -> PageRequest:
        return PageRequest(limit=self.limit, offset=self.offset)


class SearchParams(ListParams):
    """List parameters of master data that can be archived."""

    include_archived: bool = False
