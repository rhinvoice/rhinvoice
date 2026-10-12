"""VAT identification numbers (UID / USt-IdNr / UID-Nummer).

* CH: UID "CHE-123.456.789" with modulo 11 check digit
  (Bundesamt für Statistik, UID-Register). Optional suffix MWST/TVA/IVA.
* DE: "DE" + 9 digits. AT: "ATU" + 8 digits (format only, no checksum).
* Other EU countries: country prefix plus 2-13 letters/digits.
* LI and others: stored as entered (normalised whitespace), see OPEN_QUESTIONS.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rhinvoice.domain.shared.errors import ValidationError

_CH_UID = re.compile(r"^CHE[-\s]?(\d{3})[.\s]?(\d{3})[.\s]?(\d{3})(?:\s*(MWST|TVA|IVA))?$")
_DE = re.compile(r"^DE\d{9}$")
_AT = re.compile(r"^ATU\d{8}$")
_EU = re.compile(
    r"^(AT|BE|BG|CY|CZ|DK|EE|EL|ES|FI|FR|HR|HU|IE|IT|LT|LU|LV|MT|NL|PL|PT|RO|SE|SI|SK|XI)[A-Z0-9+*]{2,13}$"
)
_UID_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4)
MAX_LENGTH = 40


def _ch_check_digit(digits: str) -> int:
    """Modulo 11 check digit over the first eight digits; 10 is never assigned."""
    total = sum(int(digits[index]) * weight for index, weight in enumerate(_UID_WEIGHTS))
    return (11 - total % 11) % 11


@dataclass(frozen=True, slots=True)
class VatNumber:
    value: str

    @classmethod
    def parse(cls, raw: str) -> VatNumber:
        compact = " ".join(raw.upper().split())
        if not compact:
            raise ValidationError("vat_number", "VAT number is empty")
        if len(compact) > MAX_LENGTH:
            raise ValidationError(
                "vat_number", f"VAT number must be at most {MAX_LENGTH} characters"
            )
        if compact.startswith("CHE"):
            return cls._parse_swiss(compact)
        without_spaces = compact.replace(" ", "")
        if without_spaces.startswith("DE") and not _DE.fullmatch(without_spaces):
            raise ValidationError("vat_number", "a German VAT number has the form DE123456789")
        if without_spaces.startswith("AT") and not _AT.fullmatch(without_spaces):
            raise ValidationError("vat_number", "an Austrian VAT number has the form ATU12345678")
        if _EU.fullmatch(without_spaces) or _DE.fullmatch(without_spaces):
            return cls(without_spaces)
        return cls(compact)

    @classmethod
    def _parse_swiss(cls, compact: str) -> VatNumber:
        match = _CH_UID.fullmatch(compact)
        if match is None:
            raise ValidationError("vat_number", "a Swiss UID has the form CHE-123.456.789")
        digits = match.group(1) + match.group(2) + match.group(3)
        if _ch_check_digit(digits) != int(digits[8]):
            raise ValidationError("vat_number", "the check digit of the Swiss UID is wrong")
        canonical = f"CHE-{match.group(1)}.{match.group(2)}.{match.group(3)}"
        suffix = match.group(4)
        return cls(canonical if suffix is None else f"{canonical} {suffix}")

    @property
    def country_prefix(self) -> str:
        return self.value[:2]

    def __str__(self) -> str:
        return self.value
