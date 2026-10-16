"""Customers (debtors) of the company."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.text import clean_multiline, clean_text

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from rhinvoice.domain.shared.address import Address
    from rhinvoice.domain.shared.email import EmailAddress
    from rhinvoice.domain.shared.language import Language
    from rhinvoice.domain.shared.money import Currency
    from rhinvoice.domain.tax.vat_number import VatNumber

MAX_NUMBER = 20
MAX_NAME = 70
MAX_SHORT = 50
MAX_PHONE = 50
MAX_GROUP = 50
MAX_NOTE = 4000
MAX_BUYER_REFERENCE = 100
MAX_PAYMENT_TERMS_DAYS = 365


class CustomerKind(StrEnum):
    COMPANY = "company"
    PERSON = "person"


@dataclass(frozen=True, slots=True)
class Customer:
    id: UUID
    number: str
    kind: CustomerKind
    address: Address
    created_at: datetime
    company_name: str = ""
    salutation: str = ""
    first_name: str = ""
    last_name: str = ""
    contact_person: str = ""
    """Attention line for companies ("z. Hd.")."""
    email: EmailAddress | None = None
    phone: str = ""
    vat_number: VatNumber | None = None
    buyer_reference: str = ""
    """A fixed buyer reference (BT-10), e.g. the Leitweg-ID of a German authority.

    Set, it is the reference of every e-invoice to the customer; empty, the document's.
    """
    group: str = ""
    default_currency: Currency | None = None
    default_language: Language | None = None
    tax_exempt: bool = False
    default_discount: Decimal = Decimal(0)
    """Default discount in percent applied to new documents."""
    payment_terms_days: int | None = None
    """Overrides the company's payment terms if set."""
    delivery_address: Address | None = None
    note: str = ""
    archived: bool = False

    def __post_init__(self) -> None:
        self._set("number", clean_text(self.number, "number", max_length=MAX_NUMBER, required=True))
        self._set(
            "company_name",
            clean_text(
                self.company_name,
                "company_name",
                max_length=MAX_NAME,
                required=self.kind is CustomerKind.COMPANY,
            ),
        )
        self._set("salutation", clean_text(self.salutation, "salutation", max_length=MAX_SHORT))
        self._set("first_name", clean_text(self.first_name, "first_name", max_length=MAX_SHORT))
        self._set(
            "last_name",
            clean_text(
                self.last_name,
                "last_name",
                max_length=MAX_SHORT,
                required=self.kind is CustomerKind.PERSON,
            ),
        )
        self._set(
            "contact_person",
            clean_text(self.contact_person, "contact_person", max_length=MAX_NAME),
        )
        self._set("phone", clean_text(self.phone, "phone", max_length=MAX_PHONE))
        self._set(
            "buyer_reference",
            clean_text(self.buyer_reference, "buyer_reference", max_length=MAX_BUYER_REFERENCE),
        )
        self._set("group", clean_text(self.group, "group", max_length=MAX_GROUP))
        self._set("note", clean_multiline(self.note, "note", max_length=MAX_NOTE))
        if not Decimal(0) <= self.default_discount <= Decimal(100):
            raise ValidationError("default_discount", "discount must be between 0 and 100 percent")
        if self.payment_terms_days is not None and not (
            0 <= self.payment_terms_days <= MAX_PAYMENT_TERMS_DAYS
        ):
            raise ValidationError(
                "payment_terms_days",
                f"payment terms must be between 0 and {MAX_PAYMENT_TERMS_DAYS} days",
            )

    def _set(self, name: str, value: object) -> None:
        object.__setattr__(self, name, value)

    @property
    def is_business(self) -> bool:
        """B2B customer: decides reverse charge and the required VAT number."""
        return self.kind is CustomerKind.COMPANY

    @property
    def person_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part)

    @property
    def display_name(self) -> str:
        if self.kind is CustomerKind.COMPANY:
            return self.company_name
        return self.person_name

    def archive(self) -> Customer:
        return replace(self, archived=True)

    def restore(self) -> Customer:
        return replace(self, archived=False)
