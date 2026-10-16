"""Turn the texts of imported cells into values: amounts, countries, units, addresses.

Files from other programs and spreadsheets write values the way people type them:
"1'234.50", "1.234,50", "CHF 50.-", "Schweiz", "Std.", "Dorfstrasse 1a",
"CH-9470 Buchs SG". Values that cannot be understood raise a ValidationError
with the field name, so the row is reported instead of imported.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from rhinvoice.domain.catalog.unit import UNITS
from rhinvoice.domain.shared.country import CountryCode
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply

if TYPE_CHECKING:
    from collections.abc import Sequence

    from rhinvoice.domain.tax.rates import TaxRateSet

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def normalize(text: str) -> str:
    """Compare names regardless of case, umlauts, accents, spaces and punctuation."""
    lowered = text.strip().lower().translate(_UMLAUTS)
    plain = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", plain)


# "Dorfstrasse 1", "Dorfstrasse 1a", "Hauptstr. 12-14", "Via Roma 3/2", "Rue du Lac, 7 B"
_STREET = re.compile(
    r"^(?P<street>.*?\D)[\s,]+(?P<number>\d+\s?[a-zA-Z]?(?:\s?[-/]\s?\d+\s?[a-zA-Z]?)?)$"
)


def split_street(text: str) -> tuple[str, str]:
    """Split "Dorfstrasse 1a" into street and house number; without a number all is street."""
    value = " ".join(text.split())
    match = _STREET.match(value)
    if match is None:
        return value, ""
    return match["street"].rstrip(" ,"), match["number"].replace(" ", "")


# Postal codes with the country prefix of old letters: "CH-9470", "FL-9490", "D-10115", "A-6850".
_POSTAL_PREFIX = {
    "CH": "CH",
    "FL": "LI",
    "LI": "LI",
    "D": "DE",
    "DE": "DE",
    "A": "AT",
    "AT": "AT",
    "I": "IT",
    "IT": "IT",
    "F": "FR",
    "FR": "FR",
    "B": "BE",
    "L": "LU",
    "E": "ES",
}
_POSTAL_CITY = re.compile(
    r"^(?:(?P<prefix>[A-Za-z]{1,2})\s?-\s?)?(?P<postal>\d{4,5})\s+(?P<city>.+)$"
)


def split_postal_city(text: str) -> tuple[str, str, str]:
    """Split "CH-9470 Buchs SG" into postal code, city and the prefix's country ("" if none)."""
    value = " ".join(text.split())
    match = _POSTAL_CITY.match(value)
    if match is None:
        return "", value, ""
    prefix = (match["prefix"] or "").upper()
    country = _POSTAL_PREFIX.get(prefix, "")
    if prefix and not country:
        # Guessing the company's country would put the customer in the wrong country.
        raise ValidationError(
            "postal_city", f"unknown country prefix '{prefix}'", code="unknown_country_prefix"
        )
    return match["postal"], match["city"], country


_COUNTRY_NAMES = {
    normalize(name): code
    for code, names in {
        "CH": ("Schweiz", "Switzerland", "Suisse", "Svizzera", "CHE"),
        "LI": ("Liechtenstein", "FL", "Fürstentum Liechtenstein", "LIE"),
        "DE": ("Deutschland", "Germany", "BRD", "D", "DEU"),
        "AT": ("Österreich", "Oesterreich", "Austria", "A", "AUT"),
        "IT": ("Italien", "Italy", "Italia"),
        "FR": ("Frankreich", "France"),
        "NL": ("Niederlande", "Holland", "Netherlands"),
        "BE": ("Belgien", "Belgium"),
        "LU": ("Luxemburg", "Luxembourg"),
        "ES": ("Spanien", "Spain"),
        "PL": ("Polen", "Poland"),
        "CZ": ("Tschechien", "Czechia", "Czech Republic"),
        "GB": ("Grossbritannien", "Vereinigtes Königreich", "United Kingdom", "UK", "England"),
        "US": ("USA", "Vereinigte Staaten", "United States"),
    }.items()
    for name in names
}


def parse_country(text: str, default: str) -> str:
    """ISO code of a country name or code; empty cells take the company's country."""
    value = text.strip()
    if not value:
        return default
    known = _COUNTRY_NAMES.get(normalize(value))
    if known is not None:
        return known
    # An ISO code; CountryCode raises a ValidationError for anything else.
    return CountryCode(value.upper()).value


# Currency names and signs before or after the number: "CHF 50", "Fr. 50.-", "50 €".
_CURRENCY = re.compile(r"(?i)(?<![a-z])(?:chf|sfr\.?|fr\.?|eur|euro)(?![a-z])|[€$£]")
# "50.-" and "50.\u2013": the Swiss notation for whole francs.
_WHOLE = re.compile("(?<=\\d)[.,]?[-\u2013]+$")
# Spaces and apostrophes (also typographic ones, U+2019) group thousands: "1'234", "1 234".
_GROUPING = re.compile("(?<=\\d)[\\s'\u2019](?=\\d{3}(?!\\d))")
# What is left must be a number: digits, optionally with a sign and separators.
_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)*")
# Thousands groups: one to three digits (not starting with 0), then groups of three.
_GROUPED = re.compile(r"-?[1-9]\d{0,2}(?:[.,]\d{3})+")
# "1.500" or "12.000": a dot grouping thousands, where dots do that.
_DOT_THOUSAND = re.compile(r"-?[1-9]\d{0,2}\.\d{3}")


def _invalid_amount(text: str, field: str) -> ValidationError:
    return ValidationError(field, f"'{text}' is not an amount", code="invalid_amount")


def parse_amount(text: str, field: str, *, dot_thousands: bool = False) -> str:
    """Decimal text of an amount written with Swiss, German or English separators.

    "1'234.50", "1.234,50", "1,234.50", "CHF 50.-" and "Fr. 1'250.-" are read as
    people mean them. A single dot followed by exactly three digits ("1.500") is a
    thousands separator where dots group thousands (``dot_thousands``: DE, AT) and
    a decimal point elsewhere (CH, LI). Anything else is refused, never guessed.
    """
    value = _GROUPING.sub("", _WHOLE.sub("", _CURRENCY.sub("", text).strip()))
    if not _NUMBER.fullmatch(value):
        raise _invalid_amount(text, field)
    separators = re.findall("[.,]", value)
    if not separators:
        return str(Decimal(value))
    thousands_only = (len(separators) > 1 and len(set(separators)) == 1) or (
        separators == ["."] and dot_thousands and _DOT_THOUSAND.fullmatch(value) is not None
    )
    integer, fraction = (value, "") if thousands_only else value.rsplit(separators[-1], 1)
    groups = re.split("[.,]", integer)
    if len(groups) > 1 and _GROUPED.fullmatch(integer) is None:
        raise _invalid_amount(text, field)
    return str(Decimal("".join(groups) + (f".{fraction}" if fraction else "")))


def parse_whole_number(text: str, field: str) -> int | None:
    value = text.strip()
    if not value:
        return None
    try:
        number = Decimal(parse_amount(value, field, dot_thousands=True))
    except ValidationError:
        raise ValidationError(field, f"'{text}' is not a number", code="invalid_number") from None
    if number != number.to_integral_value():
        raise ValidationError(field, f"'{text}' is not a whole number", code="invalid_number")
    return int(number)


_UNIT_NAMES = (
    {normalize(code): code for code in UNITS}
    | {normalize(label): code for code, labels in UNITS.items() for label in labels}
    | {
        normalize(name): code
        for code, names in {
            "C62": ("Stück", "Stk", "St", "pc", "piece", "pieces", "Anzahl", "x"),
            "HUR": ("Stunde", "Stunden", "Std", "h", "hour", "hours"),
            "MIN": ("Minute", "Minuten", "minutes"),
            "DAY": ("Tage", "days", "Tg", "täglich", "pro Tag", "daily"),
            "WEE": ("Wochen", "weeks", "Wo", "wöchentlich", "pro Woche", "weekly"),
            "MON": ("Monate", "months", "Mt", "Mon", "monatlich", "pro Monat", "monthly"),
            "ANN": ("Jahre", "years", "J", "jährlich", "pro Jahr", "yearly", "annually"),
            "LS": ("Psch", "pauschal", "pausch", "flat"),
            "LTR": ("Liter", "litre", "liter"),
            "MTR": ("Meter", "metre", "meter", "lfm"),
            "KGM": ("Kilogramm", "kilogram"),
            "PR": ("Paare", "pairs"),
        }.items()
        for name in names
    }
)


def parse_unit(text: str, default: str) -> str:
    """UN/ECE code of a unit written as code or label ("Std.", "Stunden", "HUR")."""
    value = text.strip()
    if not value:
        return default
    code = _UNIT_NAMES.get(normalize(value))
    if code is None:
        raise ValidationError("unit", f"'{text}' is not a known unit", code="unknown_unit")
    return code


_TAX_CATEGORIES = {
    normalize(name): category
    for category, names in {
        TaxCategory.STANDARD: ("normal", "standard", "normalsatz", "voll"),
        TaxCategory.REDUCED: ("reduziert", "reduced", "ermaessigt", "ermässigt"),
        TaxCategory.SPECIAL: ("sondersatz", "special", "beherbergung"),
        TaxCategory.ZERO: ("null", "zero", "0"),
        TaxCategory.EXEMPT: ("befreit", "steuerfrei", "exempt", "frei"),
    }.items()
    for name in names
}


def _rate_categories(rate_sets: Sequence[TaxRateSet]) -> dict[Decimal, TaxCategory]:
    """Map every rate the country has had to its category (7.7 % and 8 % are former Swiss ones).

    A rate written in a file only says which category the article belongs to.
    """
    categories = {Decimal(0): TaxCategory.ZERO}
    for rate_set in rate_sets:
        for category in (TaxCategory.STANDARD, TaxCategory.REDUCED, TaxCategory.SPECIAL):
            if category is not TaxCategory.SPECIAL or rate_set.special is not None:
                categories.setdefault(rate_set.rate(category).normalize(), category)
    return categories


def parse_tax_category(text: str, rate_sets: Sequence[TaxRateSet]) -> TaxCategory:
    """Read a category by name or by one of the rates of the company's country."""
    value = text.strip()
    if not value:
        return TaxCategory.STANDARD
    named = _TAX_CATEGORIES.get(normalize(value))
    if named is not None:
        return named
    try:
        rate = Decimal(parse_amount(value.rstrip("%"), "tax_category"))
    except ValidationError:
        rate = None
    category = None if rate is None else _rate_categories(rate_sets).get(rate.normalize())
    if category is None:
        raise ValidationError(
            "tax_category", f"'{text}' is not a known VAT rate", code="unknown_tax_rate"
        )
    return category


_SUPPLIES = {
    normalize(name): supply
    for supply, names in {
        Supply.SERVICE: ("Dienstleistung", "Leistung", "Arbeit", "Service", "Services"),
        Supply.GOODS: ("Ware", "Waren", "Produkt", "Material", "Lieferung", "Goods", "Product"),
    }.items()
    for name in names
}


def parse_supply(text: str) -> Supply:
    """Read whether an article is goods or a service; empty is a service."""
    value = text.strip()
    if not value:
        return Supply.SERVICE
    supply = _SUPPLIES.get(normalize(value))
    if supply is None:
        raise ValidationError(
            "supply", f"'{text}' is neither goods nor a service", code="unknown_supply"
        )
    return supply


_LANGUAGES = {
    normalize(name): language
    for language, names in {
        Language.DE: ("de", "deutsch", "german", "ger", "d"),
        Language.EN: ("en", "englisch", "english", "eng", "e"),
        Language.FR: ("fr", "französisch", "french", "français", "fra", "fre", "f"),
        Language.IT: ("it", "italienisch", "italian", "italiano", "ita", "i"),
    }.items()
    for name in names
}


def parse_language(text: str) -> Language | None:
    value = text.strip()
    if not value:
        return None
    language = _LANGUAGES.get(normalize(value))
    if language is None:
        raise ValidationError(
            "default_language", f"'{text}' is not a supported language", code="unknown_language"
        )
    return language


_TITLE_WORDS = frozenset(
    {"rechnung", "rechnungsnr", "invoice", "faktura", "facture", "fattura", "nr", "no", ""}
)
_DATE_WORDS = frozenset({"vom", "from", "du", "del", "dated"})
_DATE_TOKEN = re.compile(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{4}-\d{2}-\d{2}")


def parse_document_number(text: str) -> str:
    """Read the invoice number of a cell such as "Rechnung R20150001" or "Nr. 2015-001".

    Exports often put the number into a title: the words before it and a date after it are
    left out; a number of several words ("RE 2015 001") stays whole.
    """
    words = text.split()
    # Leading words of a title: "Rechnung", "Invoice", "Nr.", "#".
    while len(words) > 1 and normalize(words[0]) in _TITLE_WORDS:
        words = words[1:]
    # A date after the number: "R2015-1 vom 12.03.2015".
    for index, word in enumerate(words[1:], start=1):
        if normalize(word) in _DATE_WORDS or _DATE_TOKEN.fullmatch(word):
            words = words[:index]
            break
    return " ".join(words).strip(".,:;()#")


def parse_currency(text: str) -> Currency | None:
    value = re.sub(r"^S?FR\.?$", "CHF", text.strip().upper().replace("€", "EUR"))
    if not value:
        return None
    try:
        return Currency(value)
    except ValueError:
        raise ValidationError(
            "default_currency", f"'{text}' is not a supported currency", code="unknown_currency"
        ) from None


_YES = frozenset({"1", "ja", "j", "yes", "y", "true", "wahr", "x"})
_NO = frozenset({"", "0", "nein", "n", "no", "false", "falsch"})


_DATES = (
    # 14.03.2019, 14.3.19, 14/03/2019, 2019-03-14, each optionally with a time
    re.compile(r"(?P<d>\d{1,2})[./](?P<m>\d{1,2})[./](?P<y>\d{4}|\d{2})"),
    re.compile(r"(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})"),
)
_TWO_DIGIT_CENTURY = 2000


def parse_date(text: str, field: str) -> date:
    """Read a date as old programs and spreadsheets write it; a time after it is ignored."""
    value = text.strip()
    for pattern in _DATES:
        match = pattern.match(value)
        if match and (len(value) == match.end() or value[match.end()] in " T"):
            year = int(match["y"])
            if year < 100:  # noqa: PLR2004 - two-digit years
                year += _TWO_DIGIT_CENTURY
            try:
                return date(year, int(match["m"]), int(match["d"]))
            except ValueError:
                break
    raise ValidationError(field, f"'{text}' is not a date", code="invalid_date")


def parse_flag(text: str, field: str) -> bool:
    value = text.strip().lower()
    if value in _YES:
        return True
    if value in _NO:
        return False
    raise ValidationError(field, f"'{text}' is neither yes nor no", code="invalid_flag")
