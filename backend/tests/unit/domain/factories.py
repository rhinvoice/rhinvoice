"""Builders for valid domain objects; tests override only what they care about."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from rhinvoice.domain.catalog.article import Article
from rhinvoice.domain.catalog.unit import Unit
from rhinvoice.domain.company.bank_account import BankAccount
from rhinvoice.domain.company.company import Company
from rhinvoice.domain.customer.customer import Customer, CustomerKind
from rhinvoice.domain.shared.address import Address
from rhinvoice.domain.shared.country import CountryCode
from rhinvoice.domain.shared.iban import Iban
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.vat_number import VatNumber

NOW = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)
CH_IBAN = "CH9300762011623852957"
CH_QR_IBAN = "CH4431999123000889012"


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
    }
    values.update(overrides)
    return Article(**values)
