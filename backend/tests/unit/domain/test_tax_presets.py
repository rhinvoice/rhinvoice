from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from rhinvoice.domain.country.registry import PROFILES, profile_of
from rhinvoice.domain.shared.country import Country
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.tax.presets import BASE_KEYS, EXEMPT, REDUCED, SPECIAL, STANDARD, ZERO
from rhinvoice.domain.tax.tax_rate import RateCategory


def percents(country: Country, key: str) -> list[tuple[date, str]]:
    preset = next(preset for preset in profile_of(country).presets if preset.key == key)
    return [(value.valid_from, str(value.percent)) for value in preset.values]


def test_base_presets_follow_the_dated_rates_of_the_country() -> None:
    assert percents(Country.CH, STANDARD) == [
        (date(2011, 1, 1), "8"),
        (date(2018, 1, 1), "7.7"),
        (date(2024, 1, 1), "8.1"),
    ]
    # Unchanged percentages are one value.
    assert percents(Country.LI, REDUCED) == [(date(2011, 1, 1), "2.5"), (date(2024, 1, 1), "2.6")]
    assert percents(Country.CH, SPECIAL) == [
        (date(2011, 1, 1), "3.8"),
        (date(2018, 1, 1), "3.7"),
        (date(2024, 1, 1), "3.8"),
    ]
    assert percents(Country.DE, STANDARD) == [
        (date(2007, 1, 1), "19"),
        (date(2020, 7, 1), "16"),
        (date(2021, 1, 1), "19"),
    ]
    assert percents(Country.AT, SPECIAL) == [(date(2016, 1, 1), "13")]
    assert percents(Country.DE, ZERO) == [(date(2007, 1, 1), "0")]


@pytest.mark.parametrize("country", list(PROFILES))
def test_every_country_starts_with_its_base_rates(country: Country) -> None:
    profile = profile_of(country)
    keys = [preset.key for preset in profile.base_presets]
    has_special = profile.terms[Language.DE].special_rate is not None
    assert keys == [key for key in BASE_KEYS if has_special or key != SPECIAL]
    for preset in profile.presets:
        rate = preset.to_rate(uuid4(), Language.FR)
        assert rate.preset == preset.key
        assert rate.name == preset.names[Language.FR]
    categories = {preset.key: preset.category for preset in profile.base_presets}
    assert categories[ZERO] is RateCategory.ZERO
    assert categories[EXEMPT] is RateCategory.EXEMPT
    assert categories[STANDARD] is RateCategory.STANDARD


def test_names_are_those_of_the_former_categories() -> None:
    swiss = {preset.key: preset for preset in profile_of(Country.CH).base_presets}
    assert swiss[STANDARD].names[Language.DE] == "Normalsatz"
    assert swiss[SPECIAL].names[Language.DE] == "Sondersatz Beherbergung"
    assert swiss[EXEMPT].names[Language.IT] == "Escluso dall’imposta"  # noqa: RUF001
    exempt = swiss[EXEMPT].to_rate(uuid4(), Language.EN)
    assert (exempt.exemption_reason, exempt.notice) == ("Exempt supply", "")
    assert swiss[STANDARD].to_rate(uuid4(), Language.DE).exemption_reason == ""


def test_german_average_rates_of_section_24() -> None:
    german = profile_of(Country.DE)
    assert [preset.key for preset in german.scheme_presets] == [
        "de_24_forestry",
        "de_24_beverages",
        "de_24_other",
    ]
    assert percents(Country.DE, "de_24_forestry") == [(date(2025, 1, 1), "5.5")]
    assert percents(Country.DE, "de_24_beverages") == [(date(2025, 1, 1), "19")]
    assert percents(Country.DE, "de_24_other") == [(date(2025, 1, 1), "7.8")]
    other = german.scheme_presets[2].to_rate(uuid4(), Language.DE)
    assert other.name == "Landwirtschaft § 24 (7,8 %)"
    assert other.notice == "Besteuerung nach Durchschnittssätzen (§ 24 UStG)"
    assert other.percent_on(date(2026, 3, 1)) == Decimal("7.8")
    assert all(preset.sources for preset in german.scheme_presets)
    assert profile_of(Country.AT).scheme_presets == ()
