# ruff: noqa: RUF001 - printed documents use typographic apostrophes, dashes and spaces.
from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

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
        (Language.EN, Country.DE, EN),
        (Language.FR, Country.CH, PrintLocale.FR_CH),
        (Language.FR, Country.LI, PrintLocale.FR_CH),
        (Language.FR, Country.DE, PrintLocale.FR),
        (Language.IT, Country.CH, PrintLocale.IT_CH),
        (Language.IT, Country.AT, PrintLocale.IT),
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
        ("1234567.5", PrintLocale.FR_CH, "1’234’567.50"),
        ("1234567.5", PrintLocale.IT_CH, "1’234’567.50"),
        ("1234567.5", PrintLocale.FR, "1\u202f234\u202f567,50"),
        ("1234567.5", PrintLocale.IT, "1.234.567,50"),
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
    assert day(date(2026, 2, 4), PrintLocale.FR_CH) == "4 février 2026"
    assert day(date(2026, 8, 1), PrintLocale.FR) == "1er août 2026"
    assert day(date(2026, 8, 2), PrintLocale.FR) == "2 août 2026"
    assert day(date(2026, 3, 1), PrintLocale.FR_CH) == "1er mars 2026"
    assert day(date(2026, 12, 31), PrintLocale.FR) == "31 décembre 2026"
    assert day(date(2026, 1, 9), PrintLocale.IT_CH) == "9 gennaio 2026"
    assert day(date(2026, 12, 31), PrintLocale.IT) == "31 dicembre 2026"
    assert percent(Decimal("2.6"), PrintLocale.FR) == "2,6\u00a0%"


@given(st.dates(), st.sampled_from(list(PrintLocale)))
def test_long_dates_name_the_month_of_their_language(value: date, locale: PrintLocale) -> None:
    """Long dates read day, month name, year; German keeps the numeric date."""
    text = day(value, locale)
    if locale.months is None:
        assert text == value.strftime("%d.%m.") + str(value.year)
    else:
        first = "er" if locale in {PrintLocale.FR, PrintLocale.FR_CH} and value.day == 1 else ""
        assert text == f"{value.day}{first} {locale.months[value.month - 1]} {value.year}"
        assert len(set(locale.months)) == 12


@given(
    st.decimals(min_value=-(10**9), max_value=10**9, places=2, allow_nan=False),
    st.sampled_from(list(PrintLocale)),
)
def test_money_reads_back_as_the_same_amount(value: Decimal, locale: PrintLocale) -> None:
    """Removing the thousands separator and reading the decimal mark gives the amount."""
    thousands, decimal = locale.separators
    text = money(value, locale)
    plain = text.replace(thousands, "").replace(decimal, ".").replace("\u2212", "-")
    assert Decimal(plain) == value


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
