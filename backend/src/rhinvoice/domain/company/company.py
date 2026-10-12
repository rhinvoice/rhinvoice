"""The company issuing documents (one per installation, see ADR 0004)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.country import Country
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.text import clean_text

if TYPE_CHECKING:
    from uuid import UUID

    from rhinvoice.domain.shared.address import Address
    from rhinvoice.domain.shared.email import EmailAddress
    from rhinvoice.domain.shared.language import Language
    from rhinvoice.domain.shared.money import Currency
    from rhinvoice.domain.tax.vat_number import VatNumber

MAX_NAME = 70
MAX_CONTACT = 100
MAX_REGISTER = 200
MAX_PAYMENT_TERMS_DAYS = 365
DEFAULT_ACCENT_HUE = 250


@dataclass(frozen=True, slots=True)
class Company:
    id: UUID
    name: str
    address: Address
    default_currency: Currency
    default_language: Language
    email: EmailAddress | None = None
    phone: str = ""
    website: str = ""
    vat_number: VatNumber | None = None
    """UID (CH/LI), USt-IdNr. (DE), UID-Nummer (AT)."""
    tax_number: str = ""
    """German "Steuernummer" or other national tax number."""
    commercial_register: str = ""
    small_business: bool = False
    """Not VAT registered (CH/LI below threshold, DE § 19 UStG, AT Kleinunternehmer)."""
    cash_rounding: bool = False
    """Round CHF totals to 0.05 (Rappenrundung)."""
    payment_terms_days: int = 30
    accent_hue: int = DEFAULT_ACCENT_HUE

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "name", clean_text(self.name, "name", max_length=MAX_NAME, required=True)
        )
        for field_name in ("phone", "website", "tax_number"):
            value = getattr(self, field_name)
            object.__setattr__(
                self, field_name, clean_text(value, field_name, max_length=MAX_CONTACT)
            )
        object.__setattr__(
            self,
            "commercial_register",
            clean_text(self.commercial_register, "commercial_register", max_length=MAX_REGISTER),
        )
        if self.address.country.value not in {country.value for country in Country}:
            raise ValidationError(
                "country",
                "the company must be located in CH, LI, DE or AT",
            )
        if not 0 <= self.payment_terms_days <= MAX_PAYMENT_TERMS_DAYS:
            raise ValidationError(
                "payment_terms_days",
                f"payment terms must be between 0 and {MAX_PAYMENT_TERMS_DAYS} days",
            )
        if not 0 <= self.accent_hue < 360:  # noqa: PLR2004 - degrees of the colour wheel
            raise ValidationError("accent_hue", "accent hue must be between 0 and 359")

    @property
    def country(self) -> Country:
        return Country(self.address.country.value)
