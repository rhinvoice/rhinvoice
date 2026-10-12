from decimal import Decimal

import pytest

from rhinvoice.domain.catalog.unit import UNITS, Unit
from rhinvoice.domain.customer.customer import CustomerKind
from rhinvoice.domain.shared.country import Country, CountryCode
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.iban import Iban
from rhinvoice.domain.shared.money import Currency
from tests.unit.domain import factories
from tests.unit.domain.factories import CH_IBAN, CH_QR_IBAN

# --- Company ---------------------------------------------------------------


def test_company_defaults_and_normalisation() -> None:
    company = factories.company(name="  Muster GmbH ", phone=" +41 44 000 00 00 ")
    assert company.name == "Muster GmbH"
    assert company.phone == "+41 44 000 00 00"
    assert company.country is Country.CH
    assert company.cash_rounding is True
    assert company.small_business is False
    assert company.payment_terms_days == 30
    assert company.accent_hue == 250


@pytest.mark.parametrize(
    ("overrides", "field", "message"),
    [
        ({"name": " "}, "name", "name is required"),
        ({"website": "x" * 101}, "website", "website must be at most 100 characters long"),
        ({"tax_number": "x" * 101}, "tax_number", "tax_number must be at most 100 characters long"),
        (
            {"commercial_register": "x" * 201},
            "commercial_register",
            "commercial_register must be at most 200 characters long",
        ),
        (
            {"address": factories.address(country=CountryCode("FR"))},
            "country",
            "the company must be located in CH, LI, DE or AT",
        ),
        (
            {"payment_terms_days": -1},
            "payment_terms_days",
            "payment terms must be between 0 and 365 days",
        ),
        (
            {"payment_terms_days": 366},
            "payment_terms_days",
            "payment terms must be between 0 and 365 days",
        ),
        ({"accent_hue": -1}, "accent_hue", "accent hue must be between 0 and 359"),
        ({"accent_hue": 360}, "accent_hue", "accent hue must be between 0 and 359"),
    ],
)
def test_company_validation(overrides: dict[str, object], field: str, message: str) -> None:
    with pytest.raises(ValidationError) as error:
        factories.company(**overrides)
    assert error.value.details == {field: message}


def test_company_boundaries_are_valid() -> None:
    assert factories.company(payment_terms_days=0, accent_hue=0).accent_hue == 0
    assert factories.company(payment_terms_days=365, accent_hue=359).payment_terms_days == 365
    for country in ("LI", "DE", "AT"):
        assert factories.company(
            address=factories.address(country=CountryCode(country))
        ).country == Country(country)


# --- Bank account -------------------------------------------------------------


def test_bank_account_without_qr_iban() -> None:
    account = factories.bank_account()
    assert account.qr_iban is None
    assert account.bic is None


def test_bank_account_with_qr_iban() -> None:
    account = factories.bank_account(
        qr_iban=Iban(CH_QR_IBAN), bank_name=" Bank ", holder=" Muster "
    )
    assert account.bank_name == "Bank"
    assert account.holder == "Muster"
    assert not account.is_default
    assert account.as_default(is_default=True).is_default
    assert not account.as_default(is_default=True).as_default(is_default=False).is_default


@pytest.mark.parametrize(
    ("overrides", "field", "message"),
    [
        ({"bank_name": ""}, "bank_name", "bank_name is required"),
        ({"holder": "x" * 71}, "holder", "holder must be at most 70 characters long"),
        ({"holder": " "}, "holder", "holder is required"),
        (
            {"iban": Iban(CH_QR_IBAN)},
            "iban",
            "this is a QR-IBAN; enter it as QR-IBAN and the regular IBAN here",
        ),
        (
            {"qr_iban": Iban(CH_IBAN)},
            "qr_iban",
            "a QR-IBAN is a CH/LI IBAN with an institution id from 30000 to 31999",
        ),
        (
            {"iban": Iban("LI21088100002324013AA"), "qr_iban": Iban(CH_QR_IBAN)},
            "qr_iban",
            "QR-IBAN and IBAN must be from the same country",
        ),
    ],
)
def test_bank_account_validation(overrides: dict[str, object], field: str, message: str) -> None:
    with pytest.raises(ValidationError) as error:
        factories.bank_account(**overrides)
    assert error.value.details == {field: message}


# --- Customer -----------------------------------------------------------------


def test_company_customer() -> None:
    customer = factories.customer(company_name=" Beispiel AG ", contact_person=" Frau Muster ")
    assert customer.display_name == "Beispiel AG"
    assert customer.is_business
    assert customer.contact_person == "Frau Muster"
    archived = customer.archive()
    assert archived.archived is True
    assert archived.restore().archived is False


def test_person_customer() -> None:
    customer = factories.customer(
        kind=CustomerKind.PERSON,
        company_name="",
        salutation="Herr",
        first_name=" Max ",
        last_name=" Muster ",
    )
    assert customer.display_name == "Max Muster"
    assert customer.person_name == "Max Muster"
    assert not customer.is_business
    assert (
        factories.customer(
            kind=CustomerKind.PERSON, company_name="", last_name="Muster"
        ).display_name
        == "Muster"
    )


@pytest.mark.parametrize(
    ("overrides", "field", "message"),
    [
        ({"number": " "}, "number", "number is required"),
        ({"number": "1" * 21}, "number", "number must be at most 20 characters long"),
        ({"company_name": ""}, "company_name", "company_name is required"),
        (
            {"kind": CustomerKind.PERSON, "company_name": "", "last_name": ""},
            "last_name",
            "last_name is required",
        ),
        ({"salutation": "x" * 51}, "salutation", "salutation must be at most 50 characters long"),
        ({"first_name": "x" * 51}, "first_name", "first_name must be at most 50 characters long"),
        (
            {"contact_person": "x" * 71},
            "contact_person",
            "contact_person must be at most 70 characters long",
        ),
        ({"phone": "1" * 51}, "phone", "phone must be at most 50 characters long"),
        ({"group": "x" * 51}, "group", "group must be at most 50 characters long"),
        ({"note": "x" * 4001}, "note", "note must be at most 4000 characters long"),
        (
            {"default_discount": Decimal("-0.01")},
            "default_discount",
            "discount must be between 0 and 100 percent",
        ),
        (
            {"default_discount": Decimal("100.01")},
            "default_discount",
            "discount must be between 0 and 100 percent",
        ),
        (
            {"payment_terms_days": -1},
            "payment_terms_days",
            "payment terms must be between 0 and 365 days",
        ),
        (
            {"payment_terms_days": 366},
            "payment_terms_days",
            "payment terms must be between 0 and 365 days",
        ),
    ],
)
def test_customer_validation(overrides: dict[str, object], field: str, message: str) -> None:
    with pytest.raises(ValidationError) as error:
        factories.customer(**overrides)
    assert error.value.details == {field: message}


def test_customer_boundaries() -> None:
    assert (
        factories.customer(default_discount=Decimal(100), payment_terms_days=365).default_discount
        == 100
    )
    assert (
        factories.customer(default_discount=Decimal(0), payment_terms_days=0).payment_terms_days
        == 0
    )
    assert factories.customer(note=" a \r\n b ").note == "a\n b"


# --- Article and unit -----------------------------------------------------------


def test_units() -> None:
    hours = Unit("HUR")
    assert hours.label_de == "Std."
    assert hours.label_en == "h"
    assert len(UNITS) >= 20
    with pytest.raises(ValidationError) as error:
        Unit("XYZ")
    assert error.value.details == {"unit": "'XYZ' is not a supported unit code"}


def test_article() -> None:
    article = factories.article(
        name=" Beratung ",
        description=" Zeile 1 \nZeile 2 ",
        prices={Currency.CHF: Decimal("150.1234"), Currency.EUR: Decimal(0)},
    )
    assert article.name == "Beratung"
    assert article.description == "Zeile 1\nZeile 2"
    assert article.price(Currency.EUR) == Decimal(0)
    assert article.price(Currency.CHF) == Decimal("150.1234")
    assert factories.article(prices={}).price(Currency.CHF) is None
    assert article.archive().archived is True
    assert article.archive().restore().archived is False
    assert factories.article(prices={Currency.CHF: Decimal("99999999.9999")}).price(Currency.CHF)


@pytest.mark.parametrize(
    ("overrides", "field", "message"),
    [
        ({"number": ""}, "number", "number is required"),
        ({"name": ""}, "name", "name is required"),
        ({"name": "x" * 121}, "name", "name must be at most 120 characters long"),
        ({"group": "x" * 51}, "group", "group must be at most 50 characters long"),
        (
            {"description": "x" * 4001},
            "description",
            "description must be at most 4000 characters long",
        ),
        (
            {"prices": {Currency.CHF: Decimal("-0.01")}},
            "prices.CHF",
            "price must be between 0 and 99999999.9999",
        ),
        (
            {"prices": {Currency.EUR: Decimal(100000000)}},
            "prices.EUR",
            "price must be between 0 and 99999999.9999",
        ),
        (
            {"prices": {Currency.CHF: Decimal("1.00001")}},
            "prices.CHF",
            "price must have at most 4 decimal places",
        ),
    ],
)
def test_article_validation(overrides: dict[str, object], field: str, message: str) -> None:
    with pytest.raises(ValidationError) as error:
        factories.article(**overrides)
    assert error.value.details == {field: message}
