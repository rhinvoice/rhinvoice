"""Units of measure as UN/ECE Recommendation 20 codes (required by EN 16931)."""

from __future__ import annotations

from dataclasses import dataclass

from rhinvoice.domain.shared.errors import ValidationError

# Code -> (German label, English label). A curated subset of Rec 20 / Rec 21.
UNITS: dict[str, tuple[str, str]] = {
    "C62": ("Stk.", "pcs"),
    "HUR": ("Std.", "h"),
    "MIN": ("Min.", "min"),
    "DAY": ("Tag", "day"),
    "WEE": ("Woche", "week"),
    "MON": ("Monat", "month"),
    "ANN": ("Jahr", "year"),
    "LS": ("Pauschal", "lump sum"),
    "KGM": ("kg", "kg"),
    "GRM": ("g", "g"),
    "TNE": ("t", "t"),
    "LTR": ("l", "l"),
    "MTR": ("m", "m"),
    "KMT": ("km", "km"),
    "MTK": ("m²", "m²"),
    "MTQ": ("m³", "m³"),
    "KWH": ("kWh", "kWh"),
    "SET": ("Set", "set"),
    "PR": ("Paar", "pair"),
    "XPK": ("Paket", "package"),
    "E48": ("Leistung", "service unit"),
}

DEFAULT_UNIT_CODE = "C62"


@dataclass(frozen=True, slots=True)
class Unit:
    code: str

    def __post_init__(self) -> None:
        if self.code not in UNITS:
            raise ValidationError("unit", f"'{self.code}' is not a supported unit code")

    @property
    def label_de(self) -> str:
        return UNITS[self.code][0]

    @property
    def label_en(self) -> str:
        return UNITS[self.code][1]
