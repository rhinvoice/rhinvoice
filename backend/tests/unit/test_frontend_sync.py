"""The frontend repeats some validation tables for instant feedback; they must not drift."""

import re
from pathlib import Path

from rhinvoice.domain.shared.country import EU_MEMBER_STATES, Country
from rhinvoice.domain.shared.iban import IBAN_LENGTHS

# Searched upwards: mutmut runs the tests from a copy below backend/mutants.
FRONTEND = next(
    parent / "frontend" / "src"
    for parent in Path(__file__).resolve().parents
    if (parent / "frontend" / "src").is_dir()
)


def test_iban_lengths_match_the_frontend() -> None:
    source = (FRONTEND / "lib" / "validation" / "iban.ts").read_text(encoding="utf-8")
    table = source[source.index("IBAN_LENGTHS") : source.index("};", source.index("IBAN_LENGTHS"))]
    frontend = {country: int(length) for country, length in re.findall(r"(\w{2}): (\d+),", table)}
    assert frontend == IBAN_LENGTHS


def _string_list(source: str, name: str, end: str) -> list[str]:
    start = source.index(name)
    return re.findall(r'"([A-Z]{2})"', source[start : source.index(end, start)])


def test_company_countries_match_the_frontend() -> None:
    """A new country profile also goes into the company form's list."""
    source = (FRONTEND / "features" / "company" / "company-form-model.ts").read_text(
        encoding="utf-8"
    )
    assert _string_list(source, "COMPANY_COUNTRIES =", ";") == [
        country.value for country in Country
    ]


def test_eu_member_states_match_the_frontend() -> None:
    source = (FRONTEND / "features" / "customers" / "customer-form-model.ts").read_text(
        encoding="utf-8"
    )
    assert set(_string_list(source, "EU_COUNTRIES", "]);")) == EU_MEMBER_STATES
