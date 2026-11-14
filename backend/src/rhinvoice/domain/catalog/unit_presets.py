"""The catalogue of units a company takes units from (ADR 0046).

Each entry has its code of the EN 16931 unit code list (checked against it), the labels in
the four document languages (French and Italian as written in Switzerland), the names that
the catalogue lists and searches, and a group. A company starts with the first 21 entries,
the fixed units of before (migration 0029) with their labels unchanged.

Hectare has no code of its own in the list (HAR is deprecated since Rec 20 revision 17):
it is sent as H18, the square hectometre, which is exactly one hectare.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.domain.catalog.unit import Unit, check_unit_code
from rhinvoice.domain.shared.language import Language

if TYPE_CHECKING:
    from uuid import UUID


class UnitGroup(StrEnum):
    """How the catalogue groups its units."""

    TIME = "time"
    QUANTITY = "quantity"
    WEIGHT = "weight"
    LENGTH = "length"
    AREA = "area"
    VOLUME = "volume"
    ENERGY = "energy"
    PACKAGING = "packaging"


type _Words = tuple[str, str, str, str]
"""German, English, French and Italian."""


LANGUAGES = (Language.DE, Language.EN, Language.FR, Language.IT)


@dataclass(frozen=True, slots=True)
class UnitPreset:
    key: str
    """The code; the catalogue has one entry per code."""
    group: UnitGroup
    label_words: _Words
    name_words: _Words

    def __post_init__(self) -> None:
        check_unit_code(self.key)

    @property
    def code(self) -> str:
        return self.key

    @property
    def labels(self) -> dict[Language, str]:
        """The label of documents in each language."""
        return dict(zip(LANGUAGES, self.label_words, strict=True))

    @property
    def names(self) -> dict[Language, str]:
        """What the catalogue lists and searches, in each language."""
        return dict(zip(LANGUAGES, self.name_words, strict=True))

    def to_unit(self, unit_id: UUID) -> Unit:
        """Return the entry as a company's unit: the German label, the others where they differ."""
        labels = self.labels
        label = labels[Language.DE]

        def own(language: Language) -> str:
            return "" if labels[language] == label else labels[language]

        return Unit(
            id=unit_id,
            code=self.code,
            label=label,
            label_en=own(Language.EN),
            label_fr=own(Language.FR),
            label_it=own(Language.IT),
            preset=self.key,
        )


_Q, _T, _W, _L = UnitGroup.QUANTITY, UnitGroup.TIME, UnitGroup.WEIGHT, UnitGroup.LENGTH
_A, _V, _E, _P = UnitGroup.AREA, UnitGroup.VOLUME, UnitGroup.ENERGY, UnitGroup.PACKAGING

PRESETS: tuple[UnitPreset, ...] = (
    UnitPreset("C62", _Q, ("Stk.", "pcs", "pce", "pz."), ("Stück", "piece", "pièce", "pezzo")),
    UnitPreset("HUR", _T, ("Std.", "h", "h", "h"), ("Stunde", "hour", "heure", "ora")),
    UnitPreset("MIN", _T, ("Min.", "min", "min", "min"), ("Minute", "minute", "minute", "minuto")),
    UnitPreset("DAY", _T, ("Tag", "day", "jour", "giorno"), ("Tag", "day", "jour", "giorno")),
    UnitPreset(
        "WEE",
        _T,
        ("Woche", "week", "semaine", "settimana"),
        ("Woche", "week", "semaine", "settimana"),
    ),
    UnitPreset("MON", _T, ("Monat", "month", "mois", "mese"), ("Monat", "month", "mois", "mese")),
    UnitPreset("ANN", _T, ("Jahr", "year", "année", "anno"), ("Jahr", "year", "année", "anno")),
    UnitPreset(
        "LS",
        _Q,
        ("Pauschal", "lump sum", "forfait", "forfait"),
        ("Pauschale", "lump sum", "forfait", "importo forfettario"),
    ),
    UnitPreset(
        "KGM", _W, ("kg", "kg", "kg", "kg"), ("Kilogramm", "kilogram", "kilogramme", "chilogrammo")
    ),
    UnitPreset("GRM", _W, ("g", "g", "g", "g"), ("Gramm", "gram", "gramme", "grammo")),
    UnitPreset("TNE", _W, ("t", "t", "t", "t"), ("Tonne", "tonne", "tonne", "tonnellata")),
    UnitPreset("LTR", _V, ("l", "l", "l", "l"), ("Liter", "litre", "litre", "litro")),
    UnitPreset("MTR", _L, ("m", "m", "m", "m"), ("Meter", "metre", "mètre", "metro")),
    UnitPreset(
        "KMT", _L, ("km", "km", "km", "km"), ("Kilometer", "kilometre", "kilomètre", "chilometro")
    ),
    UnitPreset(
        "MTK",
        _A,
        ("m²", "m²", "m²", "m²"),
        ("Quadratmeter", "square metre", "mètre carré", "metro quadrato"),
    ),
    UnitPreset(
        "MTQ",
        _V,
        ("m³", "m³", "m³", "m³"),
        ("Kubikmeter", "cubic metre", "mètre cube", "metro cubo"),
    ),
    UnitPreset(
        "KWH",
        _E,
        ("kWh", "kWh", "kWh", "kWh"),
        ("Kilowattstunde", "kilowatt hour", "kilowattheure", "chilowattora"),
    ),
    UnitPreset("SET", _Q, ("Set", "set", "set", "set"), ("Set", "set", "set", "set")),
    UnitPreset("PR", _Q, ("Paar", "pair", "paire", "paio"), ("Paar", "pair", "paire", "paio")),
    UnitPreset(
        "XPK", _P, ("Paket", "package", "paquet", "pacco"), ("Paket", "package", "paquet", "pacco")
    ),
    UnitPreset(
        "E48",
        _Q,
        ("Leistung", "service unit", "prestation", "prestazione"),
        ("Leistung", "service unit", "prestation", "prestazione"),
    ),
    # Taken from the catalogue on demand.
    UnitPreset(
        "QAN",
        _T,
        ("Quartal", "quarter", "trimestre", "trimestre"),
        ("Quartal", "quarter", "trimestre", "trimestre"),
    ),
    UnitPreset(
        "DTN",
        _W,
        ("dz", "dt", "q", "q"),
        ("Doppelzentner (100 kg)", "decitonne (100 kg)", "quintal (100 kg)", "quintale (100 kg)"),
    ),
    UnitPreset(
        "MMT",
        _L,
        ("mm", "mm", "mm", "mm"),
        ("Millimeter", "millimetre", "millimètre", "millimetro"),
    ),
    UnitPreset(
        "CMT",
        _L,
        ("cm", "cm", "cm", "cm"),
        ("Zentimeter", "centimetre", "centimètre", "centimetro"),
    ),
    UnitPreset("H18", _A, ("ha", "ha", "ha", "ha"), ("Hektar", "hectare", "hectare", "ettaro")),
    UnitPreset(
        "MLT",
        _V,
        ("ml", "ml", "ml", "ml"),
        ("Milliliter", "millilitre", "millilitre", "millilitro"),
    ),
    UnitPreset(
        "HLT", _V, ("hl", "hl", "hl", "hl"), ("Hektoliter", "hectolitre", "hectolitre", "ettolitro")
    ),
    UnitPreset(
        "MWH",
        _E,
        ("MWh", "MWh", "MWh", "MWh"),
        ("Megawattstunde", "megawatt hour", "mégawattheure", "megawattora"),
    ),
    UnitPreset(
        "XCT",
        _P,
        ("Karton", "carton", "carton", "cartone"),
        ("Karton", "carton", "carton", "cartone"),
    ),
    UnitPreset(
        "XBX",
        _P,
        ("Schachtel", "box", "boîte", "scatola"),
        ("Schachtel", "box", "boîte", "scatola"),
    ),
    UnitPreset(
        "XPX",
        _P,
        ("Palette", "pallet", "palette", "pallet"),
        ("Palette", "pallet", "palette", "pallet"),
    ),
    UnitPreset(
        "XBG",
        _P,
        ("Beutel", "bag", "sachet", "sacchetto"),
        ("Beutel", "bag", "sachet", "sacchetto"),
    ),
    UnitPreset("XSA", _P, ("Sack", "sack", "sac", "sacco"), ("Sack", "sack", "sac", "sacco")),
    UnitPreset(
        "XBO",
        _P,
        ("Flasche", "bottle", "bouteille", "bottiglia"),
        ("Flasche", "bottle", "bouteille", "bottiglia"),
    ),
)

START = PRESETS[:21]
"""What a company starts with: the units of before, in their order (migration 0029)."""


def preset_of(key: str | None) -> UnitPreset | None:
    return next((preset for preset in PRESETS if preset.key == key), None)
