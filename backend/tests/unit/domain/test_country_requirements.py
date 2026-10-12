from decimal import Decimal

import pytest

from rhinvoice.domain.company.company import Company
from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.customer.customer import Customer, CustomerKind
from rhinvoice.domain.shared.country import CountryCode
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.money import Currency, Money
from rhinvoice.domain.tax.vat_number import VatNumber
from tests.helpers import raises_exactly
from tests.unit.domain import factories


def company(country: str, **overrides: object) -> Company:
    return factories.company(address=factories.address(country=CountryCode(country)), **overrides)


def eur(amount: str) -> Money:
    return Money(Decimal(amount), Currency.EUR)


def chf(amount: str) -> Money:
    return Money(Decimal(amount), Currency.CHF)


def check_invoice_requirements(company: Company, customer: Customer, total: Money) -> None:
    profile_of(company.country).check_invoice(company, customer, total)


CUSTOMER = factories.customer()


@pytest.mark.parametrize("country", ["CH", "LI"])
def test_swiss_companies_need_their_vat_number(country: str) -> None:
    check_invoice_requirements(company(country), CUSTOMER, chf("10"))
    check_invoice_requirements(
        company(country, vat_number=None, small_business=True), CUSTOMER, chf("10")
    )
    with raises_exactly(
        ValidationError, "VAT registered companies state their VAT number (UID) on invoices"
    ) as error:
        check_invoice_requirements(company(country, vat_number=None), CUSTOMER, chf("10"))
    assert (error.value.field, error.value.code) == ("company", "company_vat_number_missing")


def test_german_companies_need_a_tax_number_except_for_small_amounts() -> None:
    plain = company("DE", vat_number=None)
    check_invoice_requirements(
        company("DE", vat_number=None, tax_number="12/345/67890"), CUSTOMER, eur("1000")
    )
    check_invoice_requirements(
        company("DE", vat_number=VatNumber.parse("DE123456789")), CUSTOMER, eur("1000")
    )
    check_invoice_requirements(plain, CUSTOMER, eur("250"))
    for total in (eur("250.01"), chf("10")):
        with raises_exactly(
            ValidationError, "invoices state the tax number or the VAT ID of the company"
        ) as error:
            check_invoice_requirements(plain, CUSTOMER, total)
        assert (error.value.field, error.value.code) == ("company", "company_tax_id_missing")
    # Small businesses state it as well.
    with pytest.raises(ValidationError):
        check_invoice_requirements(
            company("DE", vat_number=None, small_business=True), CUSTOMER, eur("1000")
        )


def test_austrian_companies_need_their_vat_number_above_400_euros() -> None:
    plain = company("AT", vat_number=None)
    check_invoice_requirements(plain, CUSTOMER, eur("400"))
    check_invoice_requirements(
        company("AT", vat_number=None, small_business=True), CUSTOMER, eur("5000")
    )
    with raises_exactly(
        ValidationError, "invoices above EUR 400 state the VAT ID (UID) of the company"
    ) as error:
        check_invoice_requirements(plain, CUSTOMER, eur("400.01"))
    assert (error.value.field, error.value.code) == ("company", "company_vat_number_missing")


def test_austrian_business_customers_need_their_vat_number_above_10000_euros() -> None:
    austrian = company("AT", vat_number=VatNumber.parse("ATU12345678"))
    business = factories.customer(address=factories.address(country=CountryCode("AT")))
    check_invoice_requirements(austrian, business, eur("10000"))
    with raises_exactly(
        ValidationError, "invoices above EUR 10'000 state the VAT ID (UID) of the customer"
    ) as error:
        check_invoice_requirements(austrian, business, eur("10000.01"))
    assert (error.value.field, error.value.code) == ("customer_id", "customer_vat_number_required")
    check_invoice_requirements(
        austrian,
        factories.customer(
            address=factories.address(country=CountryCode("AT")),
            vat_number=VatNumber.parse("ATU12345678"),
        ),
        eur("20000"),
    )
    person = factories.customer(
        kind=CustomerKind.PERSON,
        company_name="",
        first_name="Anna",
        last_name="Muster",
        address=factories.address(country=CountryCode("AT")),
    )
    check_invoice_requirements(austrian, person, eur("20000"))
    check_invoice_requirements(austrian, factories.customer(), eur("20000"))
