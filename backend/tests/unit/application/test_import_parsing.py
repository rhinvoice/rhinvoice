"""Cell texts of imported files become values; what cannot be read is reported by field."""

from datetime import date

import pytest

from rhinvoice.application.importing.fields import ImportTarget, suggest_mapping
from rhinvoice.application.importing.parsing import (
    normalize,
    parse_amount,
    parse_country,
    parse_currency,
    parse_date,
    parse_flag,
    parse_language,
    parse_supply,
    parse_tax_category,
    parse_unit,
    parse_whole_number,
    split_postal_city,
    split_street,
)
from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.shared.country import Country
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply
from tests.helpers import raises_exactly


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Kunden-Nr.", "kundennr"),
        ("  E-Mail ", "email"),
        ("Straße", "strasse"),
        ("Ländercode", "laendercode"),
        ("Größe", "groesse"),
        ("Übersicht", "uebersicht"),
        ("Café", "cafe"),
        ("PLZ/Ort", "plzort"),
    ],
)
def test_names_are_compared_without_case_umlauts_and_punctuation(text: str, expected: str) -> None:
    assert normalize(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Dorfstrasse 1", ("Dorfstrasse", "1")),
        ("Dorfstrasse 1a", ("Dorfstrasse", "1a")),
        ("Dorfstrasse 1 a", ("Dorfstrasse", "1a")),
        ("Hauptstr. 12-14", ("Hauptstr.", "12-14")),
        ("Via Roma 3/2", ("Via Roma", "3/2")),
        ("Rue du Lac, 7 B", ("Rue du Lac", "7B")),
        ("  Am   Markt   5 ", ("Am Markt", "5")),
        ("Strasse des 17. Juni 3", ("Strasse des 17. Juni", "3")),
        ("Postfach", ("Postfach", "")),
        ("Im Feld", ("Im Feld", "")),
        ("12", ("12", "")),
    ],
)
def test_streets_are_split_from_their_house_number(text: str, expected: tuple[str, str]) -> None:
    assert split_street(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("9470 Buchs SG", ("9470", "Buchs SG", "")),
        ("CH-9470 Buchs SG", ("9470", "Buchs SG", "CH")),
        ("FL-9490 Vaduz", ("9490", "Vaduz", "LI")),
        ("D-10115  Berlin", ("10115", "Berlin", "DE")),
        ("a - 6850 Dornbirn", ("6850", "Dornbirn", "AT")),
        ("I-39100 Bozen", ("39100", "Bozen", "IT")),
        ("Buchs", ("", "Buchs", "")),
        ("123 Kurz", ("", "123 Kurz", "")),
    ],
)
def test_postal_code_and_city_are_split(text: str, expected: tuple[str, str, str]) -> None:
    assert split_postal_city(text) == expected


def test_unknown_country_prefixes_are_rejected() -> None:
    with pytest.raises(ValidationError) as caught:
        split_postal_city("XY-1234 Nirgendwo")
    assert (caught.value.field, caught.value.code) == ("postal_city", "unknown_country_prefix")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", "CH"),
        ("  ", "CH"),
        ("Schweiz", "CH"),
        ("SCHWEIZ", "CH"),
        ("Österreich", "AT"),
        ("Oesterreich", "AT"),
        ("A", "AT"),
        ("Deutschland", "DE"),
        ("FL", "LI"),
        ("Liechtenstein", "LI"),
        ("it", "IT"),
        ("se", "SE"),
        ("USA", "US"),
    ],
)
def test_countries_are_read_from_names_and_codes(text: str, expected: str) -> None:
    assert parse_country(text, "CH") == expected


def test_unknown_countries_are_rejected() -> None:
    with pytest.raises(ValidationError) as caught:
        parse_country("Atlantis", "CH")
    assert caught.value.field == "country"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("120", "120"),
        ("120.50", "120.50"),
        ("120,50", "120.50"),
        ("1'234.50", "1234.50"),
        ("1\u2019234.50", "1234.50"),
        ("1.234,50", "1234.50"),
        ("1,234.50", "1234.50"),
        ("CHF 50.-", "50"),
        ("50.\u2013", "50"),
        ("EUR 9.240,00", "9240.00"),
        ("€ 12", "12"),
        ("-5", "-5"),
    ],
)
def test_amounts_are_read_with_any_separator(text: str, expected: str) -> None:
    assert parse_amount(text, "price") == expected


@pytest.mark.parametrize("text", ["abc", "", "1.2.3", "Infinity", "NaN"])
def test_text_that_is_no_amount_is_rejected(text: str) -> None:
    with pytest.raises(ValidationError) as caught:
        parse_amount(text, "price")
    assert (caught.value.field, caught.value.code) == ("price", "invalid_amount")


def test_whole_numbers() -> None:
    assert parse_whole_number("30", "days") == 30
    assert parse_whole_number("30.0", "days") == 30
    assert parse_whole_number(" ", "days") is None
    for text in ("30.5", "dreissig"):
        with pytest.raises(ValidationError) as caught:
            parse_whole_number(text, "days")
        assert (caught.value.field, caught.value.code) == ("days", "invalid_number")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", "C62"),
        ("HUR", "HUR"),
        ("Std.", "HUR"),
        ("Stunden", "HUR"),
        ("h", "HUR"),
        ("Stück", "C62"),
        ("Stk", "C62"),
        ("pcs", "C62"),
        ("Pauschal", "LS"),
        ("Psch.", "LS"),
        ("m²", "MTK"),
        ("Tag", "DAY"),
        ("Monat", "MON"),
        ("monatlich", "MON"),
        ("pro Monat", "MON"),
        ("jährlich", "ANN"),
    ],
)
def test_units_are_read_from_codes_and_labels(text: str, expected: str) -> None:
    assert parse_unit(text, "C62") == expected


def test_unknown_units_are_rejected() -> None:
    with pytest.raises(ValidationError) as caught:
        parse_unit("Fass", "C62")
    assert (caught.value.field, caught.value.code) == ("unit", "unknown_unit")


@pytest.mark.parametrize(
    ("country", "text", "expected"),
    [
        (Country.CH, "", TaxCategory.STANDARD),
        (Country.CH, "normal", TaxCategory.STANDARD),
        (Country.CH, "8.1", TaxCategory.STANDARD),
        (Country.CH, "8,1 %", TaxCategory.STANDARD),
        (Country.CH, "7.7", TaxCategory.STANDARD),
        # The standard rate of 2011 to 2017.
        (Country.CH, "8", TaxCategory.STANDARD),
        (Country.CH, "2.6", TaxCategory.REDUCED),
        (Country.CH, "2.5", TaxCategory.REDUCED),
        (Country.CH, "ermässigt", TaxCategory.REDUCED),
        (Country.CH, "3.8", TaxCategory.SPECIAL),
        (Country.LI, "3.7", TaxCategory.SPECIAL),
        (Country.CH, "Beherbergung", TaxCategory.SPECIAL),
        (Country.CH, "0", TaxCategory.ZERO),
        (Country.CH, "0.0", TaxCategory.ZERO),
        (Country.CH, "steuerfrei", TaxCategory.EXEMPT),
        (Country.DE, "19%", TaxCategory.STANDARD),
        (Country.DE, "7", TaxCategory.REDUCED),
        # The rates of the second half of 2020.
        (Country.DE, "16", TaxCategory.STANDARD),
        (Country.DE, "5", TaxCategory.REDUCED),
        (Country.AT, "20.00", TaxCategory.STANDARD),
        (Country.AT, "10", TaxCategory.REDUCED),
        # Austria's 13 % is its own rate, not the 10 % one.
        (Country.AT, "13", TaxCategory.SPECIAL),
    ],
)
def test_tax_categories_are_read_from_names_and_rates(
    country: Country, text: str, expected: TaxCategory
) -> None:
    assert parse_tax_category(text, profile_of(country).rates) is expected


@pytest.mark.parametrize(
    ("country", "text"),
    [
        (Country.CH, "5"),
        (Country.CH, "viel"),
        (Country.CH, "8.1.1"),
        (Country.CH, "19"),
        (Country.DE, "13"),
        (Country.DE, "8.1"),
    ],
)
def test_unknown_tax_rates_are_rejected(country: Country, text: str) -> None:
    with pytest.raises(ValidationError) as caught:
        parse_tax_category(text, profile_of(country).rates)
    assert (caught.value.field, caught.value.code) == ("tax_category", "unknown_tax_rate")
    assert caught.value.details == {"tax_category": f"'{text}' is not a known VAT rate"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", Supply.SERVICE),
        ("Dienstleistung", Supply.SERVICE),
        (" leistung ", Supply.SERVICE),
        ("Ware", Supply.GOODS),
        ("WAREN", Supply.GOODS),
        ("Goods", Supply.GOODS),
    ],
)
def test_goods_and_services(text: str, expected: Supply) -> None:
    assert parse_supply(text) is expected


def test_unknown_supplies_are_rejected() -> None:
    with raises_exactly(ValidationError, "'Abo' is neither goods nor a service") as caught:
        parse_supply("Abo")
    assert (caught.value.field, caught.value.code) == ("supply", "unknown_supply")


def test_languages() -> None:
    assert parse_language("") is None
    assert parse_language("Deutsch") is Language.DE
    assert parse_language("EN") is Language.EN
    with pytest.raises(ValidationError) as caught:
        parse_language("Französisch")
    assert (caught.value.field, caught.value.code) == ("default_language", "unknown_language")


def test_currencies() -> None:
    assert parse_currency(" ") is None
    assert parse_currency("chf") is Currency.CHF
    assert parse_currency("Fr.") is Currency.CHF
    assert parse_currency("€") is Currency.EUR
    with pytest.raises(ValidationError) as caught:
        parse_currency("USD")
    assert (caught.value.field, caught.value.code) == ("default_currency", "unknown_currency")


@pytest.mark.parametrize(
    ("text", "expected"),
    [("ja", True), ("X", True), ("1", True), ("", False), ("nein", False), ("0", False)],
)
def test_flags(text: str, expected: bool) -> None:
    assert parse_flag(text, "tax_exempt") is expected


def test_unclear_flags_are_rejected() -> None:
    with pytest.raises(ValidationError) as caught:
        parse_flag("vielleicht", "tax_exempt")
    assert (caught.value.field, caught.value.code) == ("tax_exempt", "invalid_flag")


def test_columns_are_suggested_by_their_usual_names() -> None:
    headers = ("KdNr", "Firma", "Strasse", "PLZ_Ort", "UID", "Bemerkung2", "E-Mail", "Name")
    assert suggest_mapping(headers, ImportTarget.CUSTOMERS) == {
        "number": 0,
        "company_name": 1,
        "street": 2,
        "postal_city": 3,
        "vat_number": 4,
        "email": 6,
    }


def test_a_column_is_suggested_for_one_field_only() -> None:
    # "Name" fits the company name and nothing else may take it; "Nr" goes to the number.
    headers = ("Name", "Nr", "Nachname", "Vorname", "Ort", "PLZ")
    assert suggest_mapping(headers, ImportTarget.CUSTOMERS) == {
        "number": 1,
        "company_name": 0,
        "first_name": 3,
        "last_name": 2,
        "postal_code": 5,
        "city": 4,
    }


def test_article_columns_are_suggested() -> None:
    headers = ("Art.-Nr.", "Bezeichnung", "Langtext", "Einheit", "VK", "MwSt", "Unbekannt")
    assert suggest_mapping(headers, ImportTarget.ARTICLES) == {
        "number": 0,
        "name": 1,
        "description": 2,
        "unit": 3,
        "price": 4,
        "tax_category": 5,
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("14.03.2019", date(2019, 3, 14)),
        ("4.3.2019", date(2019, 3, 4)),
        ("14.03.19", date(2019, 3, 14)),
        ("14/03/2019", date(2019, 3, 14)),
        ("2019-03-14", date(2019, 3, 14)),
        ("2019-03-14T10:22:00", date(2019, 3, 14)),
        (" 14.03.2019 10:22 ", date(2019, 3, 14)),
    ],
)
def test_dates_are_read_as_old_programs_write_them(text: str, expected: date) -> None:
    assert parse_date(text, "customer_since") == expected


@pytest.mark.parametrize("text", ["morgen", "31.02.2019", "2019-13-01", "14.03.2019x", "1403"])
def test_what_is_no_date_is_reported(text: str) -> None:
    with raises_exactly(ValidationError, f"'{text}' is not a date") as caught:
        parse_date(text, "customer_since")
    assert (caught.value.field, caught.value.code) == ("customer_since", "invalid_date")
