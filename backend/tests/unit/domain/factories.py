"""Builders for valid domain objects; tests override only what they care about."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, UUID, uuid5

from rhinvoice.domain.catalog.article import Article
from rhinvoice.domain.catalog.unit import Unit
from rhinvoice.domain.company.bank_account import BankAccount
from rhinvoice.domain.company.company import Company
from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.customer.customer import Customer, CustomerKind
from rhinvoice.domain.shared.address import Address
from rhinvoice.domain.shared.country import Country, CountryCode
from rhinvoice.domain.shared.iban import Iban
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.presets import STANDARD
from rhinvoice.domain.tax.vat_number import VatNumber

if TYPE_CHECKING:
    from rhinvoice.domain.tax.tax_rate import TaxRate

NOW = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)
CH_IBAN = "CH9300762011623852957"
CH_QR_IBAN = "CH4431999123000889012"


def rate_id(preset: str = STANDARD) -> UUID:
    """Return the id of a preset's rate in every test installation, the same in each country."""
    return uuid5(NAMESPACE_URL, f"rhinvoice-test:{preset}")


def tax_rates(
    country: Country = Country.CH, language: Language = Language.DE
) -> dict[UUID, TaxRate]:
    """Return the rates a company of ``country`` starts with (ADR 0044), under :func:`rate_id`."""
    return {
        rate_id(preset.key): preset.to_rate(rate_id(preset.key), language)
        for preset in profile_of(country).base_presets
    }


def address(**overrides: Any) -> Address:  # noqa: ANN401 - test builder
    values: dict[str, Any] = {
        "street": "Bahnhofstrasse",
        "house_number": "1",
        "postal_code": "8001",
        "city": "Zürich",
        "country": CountryCode("CH"),
    }
    values.update(overrides)
    return Address(**values)


def company(**overrides: Any) -> Company:  # noqa: ANN401
    values: dict[str, Any] = {
        "id": new_id(),
        "name": "Muster GmbH",
        "address": address(),
        "default_currency": Currency.CHF,
        "default_language": Language.DE,
        # Invoices of VAT registered companies need it (its country profile).
        "vat_number": VatNumber.parse("CHE-123.456.788 MWST"),
        # The 5-centime rounding is off by default; the Swiss test company uses it.
        "cash_rounding": True,
    }
    values.update(overrides)
    return Company(**values)


def bank_account(**overrides: Any) -> BankAccount:  # noqa: ANN401
    values: dict[str, Any] = {
        "id": new_id(),
        "currency": Currency.CHF,
        "bank_name": "Musterbank",
        "holder": "Muster GmbH",
        "iban": Iban(CH_IBAN),
    }
    values.update(overrides)
    return BankAccount(**values)


def customer(**overrides: Any) -> Customer:  # noqa: ANN401
    values: dict[str, Any] = {
        "id": new_id(),
        "number": "1001",
        "kind": CustomerKind.COMPANY,
        "company_name": "Beispiel AG",
        "address": address(street="Marktgasse", house_number="5", postal_code="3011", city="Bern"),
        "created_at": NOW,
    }
    values.update(overrides)
    return Customer(**values)


def article(**overrides: Any) -> Article:  # noqa: ANN401
    values: dict[str, Any] = {
        "id": new_id(),
        "number": "1",
        "name": "Beratung",
        "unit": Unit("HUR"),
        "tax_category": TaxCategory.STANDARD,
        "prices": {Currency.CHF: Decimal("150.00")},
        "created_at": NOW,
        "tax_rate_id": rate_id(),
    }
    values.update(overrides)
    return Article(**values)
