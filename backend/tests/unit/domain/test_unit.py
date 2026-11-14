"""The company's units and the catalogue they come from (ADR 0046)."""

import pytest

from rhinvoice.domain.catalog.unit import (
    MAX_UNIT_DESCRIPTION,
    MAX_UNIT_LABEL,
    UNIT_CODES,
    LineUnit,
    Unit,
    check_unit_code,
    known_unit,
)
from rhinvoice.domain.catalog.unit_presets import (
    PRESETS,
    START,
    UnitGroup,
    UnitPreset,
    preset_of,
)
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from tests.helpers import raises_exactly
from tests.unit.domain import factories

UNITS_OF_BEFORE = {
    # The fixed units before 0029 printed these labels in German, English, French, Italian.
    "C62": ("Stk.", "pcs", "pce", "pz."),
    "HUR": ("Std.", "h", "h", "h"),
    "MIN": ("Min.", "min", "min", "min"),
    "DAY": ("Tag", "day", "jour", "giorno"),
    "WEE": ("Woche", "week", "semaine", "settimana"),
    "MON": ("Monat", "month", "mois", "mese"),
    "ANN": ("Jahr", "year", "année", "anno"),
    "LS": ("Pauschal", "lump sum", "forfait", "forfait"),
    "KGM": ("kg", "kg", "kg", "kg"),
    "GRM": ("g", "g", "g", "g"),
    "TNE": ("t", "t", "t", "t"),
    "LTR": ("l", "l", "l", "l"),
    "MTR": ("m", "m", "m", "m"),
    "KMT": ("km", "km", "km", "km"),
    "MTK": ("m²", "m²", "m²", "m²"),
    "MTQ": ("m³", "m³", "m³", "m³"),
    "KWH": ("kWh", "kWh", "kWh", "kWh"),
    "SET": ("Set", "set", "set", "set"),
    "PR": ("Paar", "pair", "paire", "paio"),
    "XPK": ("Paket", "package", "paquet", "pacco"),
    "E48": ("Leistung", "service unit", "prestation", "prestazione"),
}
LANGUAGES = (Language.DE, Language.EN, Language.FR, Language.IT)


def unit(**overrides: object) -> Unit:
    values: dict[str, object] = {"id": new_id(), "code": "DTN", "label": "dz"}
    values.update(overrides)
    return Unit(**values)  # type: ignore[arg-type]  # test builder


# --- The code list -------------------------------------------------------------------


def test_the_code_list_is_that_of_en_16931() -> None:
    assert len(UNIT_CODES) == 2162
    assert UNIT_CODES["C62"] == "one"
    assert UNIT_CODES["DTN"] == "decitonne"
    assert UNIT_CODES["H18"] == "square hectometre"
    assert UNIT_CODES["XPX"] == "Pallet"
    # Rec 21 code missing in the KoSIT list, named after the Peppol list.
    assert UNIT_CODES["XSX"] == "Set"
    # Deprecated in Rec 20 revision 17: the validators refuse it.
    assert "HAR" not in UNIT_CODES
    assert all(1 < len(code) <= 3 for code in UNIT_CODES)
    with pytest.raises(TypeError):
        UNIT_CODES["HAR"] = "hectare"  # type: ignore[index]  # read-only


def test_codes_are_checked() -> None:
    check_unit_code("DTN")
    with raises_exactly(ValidationError, "'HAR' is not in the EN 16931 unit code list") as error:
        check_unit_code("HAR")
    assert error.value.code == "unit_code_unknown"
    assert error.value.field == "code"


# --- A unit --------------------------------------------------------------------------


def test_a_unit_prints_its_label_in_each_language() -> None:
    quintal = unit(label=" dz ", label_en=" dt ", label_it="q", description=" 100 kg ")
    assert (quintal.label, quintal.label_en, quintal.label_fr, quintal.label_it) == (
        "dz",
        "dt",
        "",
        "q",
    )
    assert quintal.description == "100 kg"
    assert quintal.translations == {Language.EN: "dt", Language.IT: "q"}
    # French has no label of its own: the main label.
    assert [quintal.label_in(language) for language in LANGUAGES] == ["dz", "dt", "dz", "q"]
    assert quintal.frozen(Language.EN) == LineUnit(code="DTN", label="dt")
    assert quintal.frozen(Language.FR) == LineUnit(code="DTN", label="dz")
    assert (quintal.preset, quintal.hidden) == (None, False)


def test_a_unit_needs_a_label_and_a_known_code() -> None:
    with raises_exactly(ValidationError, "label is required"):
        unit(label=" ")
    with raises_exactly(ValidationError, "'dz' is not in the EN 16931 unit code list"):
        unit(code="dz")


@pytest.mark.parametrize(
    ("field", "limit"),
    [
        ("label", MAX_UNIT_LABEL),
        ("label_de", MAX_UNIT_LABEL),
        ("label_en", MAX_UNIT_LABEL),
        ("label_fr", MAX_UNIT_LABEL),
        ("label_it", MAX_UNIT_LABEL),
        ("description", MAX_UNIT_DESCRIPTION),
    ],
)
def test_texts_of_a_unit_are_limited(field: str, limit: int) -> None:
    assert (MAX_UNIT_LABEL, MAX_UNIT_DESCRIPTION) == (20, 100)
    assert getattr(unit(**{field: "x" * limit}), field) == "x" * limit
    with raises_exactly(ValidationError, f"{field} must be at most {limit} characters long"):
        unit(**{field: "x" * (limit + 1)})
    with raises_exactly(
        ValidationError, f"{field} must not contain line breaks or control characters"
    ):
        unit(**{field: "a\nb"})


def test_known_units() -> None:
    hours = factories.units()[factories.unit_id("HUR")]
    assert known_unit(hours.id, factories.units()) is not None
    assert known_unit(hours.id, {hours.id: hours}) == hours
    with raises_exactly(ValidationError, "unknown unit") as error:
        known_unit(new_id(), {hours.id: hours})
    assert (error.value.field, error.value.code) == ("unit_id", "unit_unknown")


# --- The catalogue ---------------------------------------------------------------------


def test_a_company_starts_with_the_units_of_before() -> None:
    assert [preset.key for preset in START] == list(UNITS_OF_BEFORE)
    for preset in START:
        assert (
            tuple(preset.labels[language] for language in LANGUAGES)
            == (UNITS_OF_BEFORE[preset.key])
        )
    assert PRESETS[: len(START)] == START


def test_the_catalogue() -> None:
    keys = [preset.key for preset in PRESETS]
    assert len(keys) == len(set(keys))
    assert {"DTN", "H18", "MMT", "CMT", "MLT", "XCT", "XPX", "XBX", "XBG"} <= set(keys)
    assert all(preset.code == preset.key and preset.key in UNIT_CODES for preset in PRESETS)
    for preset in PRESETS:
        assert set(preset.labels) == set(preset.names) == set(LANGUAGES)
        assert all(preset.labels.values())
        assert all(preset.names.values())
    labels = [preset.labels[Language.DE].casefold() for preset in PRESETS]
    assert len(labels) == len(set(labels))
    quintal = preset_of("DTN")
    assert quintal is not None
    assert quintal.group is UnitGroup.WEIGHT
    assert quintal.labels == {
        Language.DE: "dz",
        Language.EN: "dt",
        Language.FR: "q",
        Language.IT: "q",
    }
    assert quintal.names[Language.DE] == "Doppelzentner (100 kg)"
    hectare = preset_of("H18")
    assert hectare is not None
    assert (hectare.group, hectare.names[Language.EN]) == (UnitGroup.AREA, "hectare")
    assert {preset.group for preset in PRESETS} == set(UnitGroup)
    assert preset_of("HAR") is None
    assert preset_of(None) is None


def test_an_entry_becomes_a_unit() -> None:
    unit_id = new_id()
    piece = preset_of("C62")
    assert piece is not None
    assert piece.to_unit(unit_id) == Unit(
        id=unit_id,
        code="C62",
        label="Stk.",
        label_en="pcs",
        label_fr="pce",
        label_it="pz.",
        preset="C62",
    )
    # Labels like the main one are no labels of their own: renaming the unit renames them.
    kilogram = preset_of("KGM")
    assert kilogram is not None
    assert kilogram.to_unit(unit_id).translations == {}
    hours = preset_of("HUR")
    assert hours is not None
    assert hours.to_unit(unit_id).translations == {
        Language.EN: "h",
        Language.FR: "h",
        Language.IT: "h",
    }


def test_an_entry_speaks_the_company_language() -> None:
    unit_id = new_id()
    piece = preset_of("C62")
    assert piece is not None
    french = piece.to_unit(unit_id, Language.FR)
    assert french == Unit(
        id=unit_id,
        code="C62",
        label="pce",
        label_de="Stk.",
        label_en="pcs",
        label_it="pz.",
        preset="C62",
    )
    # Every document prints what it did before.
    assert [french.label_in(language) for language in LANGUAGES] == ["Stk.", "pcs", "pce", "pz."]
    hours = preset_of("HUR")
    assert hours is not None
    assert hours.to_unit(unit_id, Language.EN).translations == {Language.DE: "Std."}
    assert unit(label="Std", label_de="Std.").label_in(Language.DE) == "Std."


def test_an_entry_has_a_known_code() -> None:
    with raises_exactly(ValidationError, "'HAR' is not in the EN 16931 unit code list"):
        UnitPreset(
            "HAR",
            UnitGroup.AREA,
            ("ha", "ha", "ha", "ha"),
            ("Hektar", "hectare", "hectare", "ettaro"),
        )
