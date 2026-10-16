"""Numbers and dates as printed on documents, per print locale.

de-CH: 1'234.50 (typographic apostrophe), de-DE/de-AT: 1.234,50, en: 1,234.50.
French and Italian follow the country like German does: Swiss and Liechtenstein
companies write 1'234.50 in both (CLDR it-CH; for French a choice, CLDR fr-CH
writes 1 234,50, see ADR 0027), German and Austrian companies 1 234,50 in
French and 1.234,50 in Italian (CLDR fr, it).
Dates: 14.02.2026 in German, 14 February 2026 in English, 14 février 2026 in
French, 14 febbraio 2026 in Italian (CLDR long dates, as Intl.DateTimeFormat).
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

_FRENCH_MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)
_ITALIAN_MONTHS = (
    "gennaio",
    "febbraio",
    "marzo",
    "aprile",
    "maggio",
    "giugno",
    "luglio",
    "agosto",
    "settembre",
    "ottobre",
    "novembre",
    "dicembre",
)


# Written as code points: the characters look like ASCII ones in the source.
APOSTROPHE = chr(0x2019)
MINUS = chr(0x2212)
NO_BREAK_SPACE = chr(0x00A0)
NARROW_NO_BREAK_SPACE = chr(0x202F)


class PrintLocale(StrEnum):
    DE_CH = "de-CH"
    DE_DE = "de-DE"
    EN = "en"
    FR_CH = "fr-CH"
    FR = "fr"
    IT_CH = "it-CH"
    IT = "it"

    @classmethod
    def of(cls, language: Language, style: NumberStyle) -> PrintLocale:
        """English documents use English numbers, the others the style of the country."""
        swiss = style is NumberStyle.APOSTROPHE
        return {
            Language.DE: cls.DE_CH if swiss else cls.DE_DE,
            Language.EN: cls.EN,
            Language.FR: cls.FR_CH if swiss else cls.FR,
            Language.IT: cls.IT_CH if swiss else cls.IT,
        }[language]

    @property
    def separators(self) -> tuple[str, str]:
        """(thousands, decimal)."""
        if self in {PrintLocale.DE_CH, PrintLocale.FR_CH, PrintLocale.IT_CH}:
            return (APOSTROPHE, ".")
        if self in {PrintLocale.DE_DE, PrintLocale.IT}:
            return (".", ",")
        if self is PrintLocale.FR:
            return (NARROW_NO_BREAK_SPACE, ",")
        return (",", ".")

    @property
    def months(self) -> tuple[str, ...] | None:
        """Month names of the long dates; None for German, which writes 14.02.2026."""
        if self is PrintLocale.EN:
            return _ENGLISH_MONTHS
        if self in {PrintLocale.FR_CH, PrintLocale.FR}:
            return _FRENCH_MONTHS
        if self in {PrintLocale.IT_CH, PrintLocale.IT}:
            return _ITALIAN_MONTHS
        return None


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


_FIRST_OF_MONTH = {
    PrintLocale.FR: "er",
    PrintLocale.FR_CH: "er",
    PrintLocale.IT: "°",
    PrintLocale.IT_CH: "°",
}


def day(value: date, locale: PrintLocale) -> str:
    months = locale.months
    if months is None:
        return f"{value.day:02d}.{value.month:02d}.{value.year}"
    # French and Italian write the first of the month as an ordinal: "1er août", "1° agosto".
    first = _FIRST_OF_MONTH.get(locale, "") if value.day == 1 else ""
    return f"{value.day}{first} {months[value.month - 1]} {value.year}"
