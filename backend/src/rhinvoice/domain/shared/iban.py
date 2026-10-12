"""IBAN and BIC validation (ISO 13616 / ISO 9362).

Lengths per country from the SWIFT IBAN Registry. Example IBANs used in tests
come from the registry, SIX and the EPC.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rhinvoice.domain.shared.errors import ValidationError

IBAN_LENGTHS: dict[str, int] = {
    "BI": 27, "DJ": 27, "FK": 18, "HN": 28, "LY": 25, "MN": 20, "NI": 28, "OM": 23,
    "RU": 33, "SD": 18, "SO": 23, "YE": 30,
    "AD": 24, "AE": 23, "AL": 28, "AT": 20, "AZ": 28, "BA": 20, "BE": 16, "BG": 22,
    "BH": 22, "BR": 29, "BY": 28, "CH": 21, "CR": 22, "CY": 28, "CZ": 24, "DE": 22,
    "DK": 18, "DO": 28, "EE": 20, "EG": 29, "ES": 24, "FI": 18, "FO": 18, "FR": 27,
    "GB": 22, "GE": 22, "GI": 23, "GL": 18, "GR": 27, "GT": 28, "HR": 21, "HU": 28,
    "IE": 22, "IL": 23, "IQ": 23, "IS": 26, "IT": 27, "JO": 30, "KW": 30, "KZ": 20,
    "LB": 28, "LC": 32, "LI": 21, "LT": 20, "LU": 20, "LV": 21, "MC": 27, "MD": 24,
    "ME": 22, "MK": 19, "MR": 27, "MT": 31, "MU": 30, "NL": 18, "NO": 15, "PK": 24,
    "PL": 28, "PS": 29, "PT": 25, "QA": 29, "RO": 24, "RS": 22, "SA": 24, "SC": 31,
    "SE": 24, "SI": 19, "SK": 24, "SM": 27, "ST": 25, "SV": 28, "TL": 23, "TN": 24,
    "TR": 26, "UA": 29, "VA": 22, "VG": 24, "XK": 20,
}  # fmt: skip

_IBAN_SHAPE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]+$")
_BIC_SHAPE = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")

# QR-IBANs carry an institution id (IID, positions 5-9) from 30000 to 31999.
QR_IID_MIN = 30000
QR_IID_MAX = 31999


def _mod97(iban: str) -> int:
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(char, 36)) for char in rearranged)
    return int(digits) % 97


@dataclass(frozen=True, slots=True)
class Iban:
    value: str
    """Electronic format: upper case without spaces."""

    def __post_init__(self) -> None:
        iban = self.value
        if not _IBAN_SHAPE.fullmatch(iban):
            raise ValidationError("iban", "IBAN must start with a country code and two digits")
        expected = IBAN_LENGTHS.get(iban[:2])
        if expected is None:
            raise ValidationError("iban", f"IBANs from {iban[:2]} are not supported")
        if len(iban) != expected:
            raise ValidationError(
                "iban",
                f"an IBAN from {iban[:2]} has {expected} characters, got {len(iban)}",
            )
        if _mod97(iban) != 1:
            raise ValidationError("iban", "IBAN check digits are wrong, please check for typos")

    @classmethod
    def parse(cls, raw: str) -> Iban:
        return cls("".join(raw.split()).upper())

    @property
    def country(self) -> str:
        return self.value[:2]

    @property
    def is_qr_iban(self) -> bool:
        """True for Swiss/Liechtenstein QR-IBANs (IID 30000-31999)."""
        if self.country not in {"CH", "LI"}:
            return False
        return QR_IID_MIN <= int(self.value[4:9]) <= QR_IID_MAX

    def formatted(self) -> str:
        """Paper format in groups of four characters."""
        return " ".join(self.value[index : index + 4] for index in range(0, len(self.value), 4))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Bic:
    value: str

    def __post_init__(self) -> None:
        if not _BIC_SHAPE.fullmatch(self.value):
            raise ValidationError("bic", "BIC must have 8 or 11 characters, e.g. UBSWCHZH80A")

    @classmethod
    def parse(cls, raw: str) -> Bic:
        return cls("".join(raw.split()).upper())

    def __str__(self) -> str:
        return self.value
