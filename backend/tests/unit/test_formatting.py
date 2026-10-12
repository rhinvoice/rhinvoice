# ruff: noqa: RUF001 - printed documents use typographic apostrophes, dashes and spaces.
from datetime import date
from decimal import Decimal

import pytest

from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.shared.country import Country
from rhinvoice.domain.shared.language import Language
from rhinvoice.infrastructure.rendering.formatting import (
    PrintLocale,
    day,
    money,
    number,
    percent,
    unit_price,
)

CH, DE, EN = PrintLocale.DE_CH, PrintLocale.DE_DE, PrintLocale.EN


@pytest.mark.parametrize(
    ("language", "country", "expected"),
    [
        (Language.DE, Country.CH, CH),
        (Language.DE, Country.LI, CH),
        (Language.DE, Country.DE, DE),
        (Language.DE, Country.AT, DE),
        (Language.EN, Country.CH, EN),
    ],
)
def test_locale_of(language: Language, country: Country, expected: PrintLocale) -> None:
    assert PrintLocale.of(language, profile_of(country).number_style) is expected


@pytest.mark.parametrize(
    ("value", "locale", "expected"),
    [
        ("1234567.5", CH, "1’234’567.50"),
        ("1234567.5", DE, "1.234.567,50"),
        ("1234567.5", EN, "1,234,567.50"),
        ("0", CH, "0.00"),
        ("999.999", CH, "1’000.00"),
        ("-12.3", DE, "−12,30"),
        ("0.125", CH, "0.13"),
        ("0.135", CH, "0.14"),
        ("123", EN, "123.00"),
        ("1234", EN, "1,234.00"),
    ],
)
def test_money(value: str, locale: PrintLocale, expected: str) -> None:
    assert money(Decimal(value), locale) == expected


@pytest.mark.parametrize(
    ("value", "locale", "expected"),
    [
        ("2.500", CH, "2.5"),
        ("2.500", DE, "2,5"),
        ("100", CH, "100"),
        ("100.00", DE, "100"),
        ("1E+3", EN, "1,000"),
        ("0.125", EN, "0.125"),
        ("12000.5", CH, "12’000.5"),
    ],
)
def test_number_drops_trailing_zeros(value: str, locale: PrintLocale, expected: str) -> None:
    assert number(Decimal(value), locale) == expected


def test_percent_and_dates() -> None:
    assert percent(Decimal("8.10"), CH) == "8.1 %"
    assert percent(Decimal(19), DE) == "19 %"
    assert day(date(2026, 2, 4), CH) == "04.02.2026"
    assert day(date(2026, 2, 4), DE) == "04.02.2026"
    assert day(date(2026, 2, 4), EN) == "4 February 2026"
    assert day(date(2026, 12, 31), EN) == "31 December 2026"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("120", "120.00"),
        ("120.5", "120.50"),
        ("0.125", "0.125"),
        ("0.1250", "0.125"),
        ("1234.5678", "1\u2019234.5678"),
        ("0.00005", "0.0001"),
        ("1E+2", "100.00"),
    ],
)
def test_unit_prices_keep_their_decimals(value: str, expected: str) -> None:
    assert unit_price(Decimal(value), CH) == expected
