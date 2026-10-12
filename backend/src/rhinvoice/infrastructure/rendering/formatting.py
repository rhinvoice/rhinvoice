"""Numbers and dates as printed on documents, per print locale.

de-CH: 1'234.50 (typographic apostrophe), de-DE/de-AT: 1.234,50, en: 1,234.50.
Dates: 14.02.2026 in German, 14 February 2026 in English.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.domain.country.profile import NumberStyle
from rhinvoice.domain.shared.language import Language

if TYPE_CHECKING:
    from datetime import date

_ENGLISH_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


# Written as code points: the characters look like ASCII ones in the source.
APOSTROPHE = chr(0x2019)
MINUS = chr(0x2212)
NO_BREAK_SPACE = chr(0x00A0)


class PrintLocale(StrEnum):
    DE_CH = "de-CH"
    DE_DE = "de-DE"
    EN = "en"

    @classmethod
    def of(cls, language: Language, style: NumberStyle) -> PrintLocale:
        """English documents use English numbers, German ones the style of the country."""
        if language is Language.EN:
            return cls.EN
        return cls.DE_CH if style is NumberStyle.APOSTROPHE else cls.DE_DE

    @property
    def separators(self) -> tuple[str, str]:
        """(thousands, decimal)."""
        if self is PrintLocale.DE_CH:
            return (APOSTROPHE, ".")
        if self is PrintLocale.DE_DE:
            return (".", ",")
        return (",", ".")


def _grouped(integer: str, separator: str) -> str:
    groups: list[str] = []
    while len(integer) > 3:  # noqa: PLR2004 - digits per group
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    groups.insert(0, integer)
    return separator.join(groups)


def number(value: Decimal, locale: PrintLocale, *, places: int | None = None) -> str:
    """Format with grouping; ``places`` fixes the decimals, None drops trailing zeros."""
    thousands, decimal = locale.separators
    if places is None:
        normalized = value.normalize()
        # normalize() writes 100 as 1E+2; quantize back to whole numbers then.
        exponent = normalized.as_tuple().exponent
        if isinstance(exponent, int) and exponent > 0:
            normalized = normalized.quantize(Decimal(1))
        text = f"{normalized:f}"
    else:
        # Commercial rounding, as everywhere else (Python's format rounds half to even).
        text = f"{value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP):f}"
    negative = text.startswith("-")
    integer, _, fraction = text.lstrip("-").partition(".")
    result = _grouped(integer, thousands) + (decimal + fraction if fraction else "")
    return f"{MINUS}{result}" if negative else result


def money(value: Decimal, locale: PrintLocale) -> str:
    return number(value, locale, places=2)


def unit_price(value: Decimal, locale: PrintLocale) -> str:
    """Prices of lines: at least 2 decimals, up to the 4 a price may have (0.125 stays 0.125)."""
    exponent = value.normalize().as_tuple().exponent
    decimals = -exponent if isinstance(exponent, int) and exponent < 0 else 0
    return number(value, locale, places=min(max(decimals, 2), 4))


def percent(value: Decimal, locale: PrintLocale) -> str:
    return f"{number(value, locale)}{NO_BREAK_SPACE}%"


def day(value: date, locale: PrintLocale) -> str:
    if locale is PrintLocale.EN:
        return f"{value.day} {_ENGLISH_MONTHS[value.month - 1]} {value.year}"
    return f"{value.day:02d}.{value.month:02d}.{value.year}"
