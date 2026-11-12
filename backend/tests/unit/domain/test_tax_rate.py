from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.tax_rate import (
    MAX_RATE_NAME,
    MAX_RATE_TEXT,
    MAX_RATE_VALUES,
    FrozenRate,
    RateCategory,
    RateValue,
    TaxRate,
)


def value(on: date, percent: str) -> RateValue:
    return RateValue(on, Decimal(percent))


def rate(**changes: object) -> TaxRate:
    fields: dict[str, object] = {
        "id": uuid4(),
        "name": "Normalsatz",
        "category": RateCategory.STANDARD,
        "values": (value(date(2018, 1, 1), "7.7"), value(date(2024, 1, 1), "8.1")),
    }
    fields.update(changes)
    return TaxRate(**fields)  # type: ignore[arg-type] # built from the defaults above


def refused(field: str, message: str, code: str | None = None, **changes: object) -> None:
    with pytest.raises(ValidationError) as error:
        rate(**changes)
    assert error.value.details == {field: message}
    if code is not None:
        assert error.value.code == code


def test_percentage_on_the_date_of_supply() -> None:
    standard = rate()
    assert standard.percent_on(date(2018, 1, 1)) == Decimal("7.7")
    assert standard.percent_on(date(2023, 12, 31)) == Decimal("7.7")
    assert standard.percent_on(date(2024, 1, 1)) == Decimal("8.1")
    assert standard.percent_on(date(2030, 6, 1)) == Decimal("8.1")


def test_no_percentage_before_the_first_date() -> None:
    with pytest.raises(ValidationError) as error:
        rate().percent_on(date(2017, 12, 31))
    assert error.value.code == "rate_not_yet_valid"
    assert error.value.details == {
        "service_date": "the rate 'Normalsatz' has no percentage before 2018-01-01"
    }


def test_texts_are_cleaned_and_limited() -> None:
    cleaned = rate(name="  Ermässigt ", notice=" § 24 UStG ", exemption_reason=" ")
    assert (cleaned.name, cleaned.notice, cleaned.exemption_reason) == (
        "Ermässigt",
        "§ 24 UStG",
        "",
    )
    assert rate(name="x" * MAX_RATE_NAME).name == "x" * MAX_RATE_NAME
    with pytest.raises(ValidationError) as error:
        rate(name=" ")
    assert error.value.field == "name"
    with pytest.raises(ValidationError) as error:
        rate(name="x" * (MAX_RATE_NAME + 1))
    assert error.value.field == "name"
    assert rate(notice="x" * MAX_RATE_TEXT).notice == "x" * MAX_RATE_TEXT
    with pytest.raises(ValidationError) as error:
        rate(notice="x" * (MAX_RATE_TEXT + 1))
    assert error.value.field == "notice"
    with pytest.raises(ValidationError) as error:
        rate(
            category=RateCategory.EXEMPT,
            values=(value(date(2024, 1, 1), "0"),),
            exemption_reason="x" * (MAX_RATE_TEXT + 1),
        )
    assert error.value.field == "exemption_reason"


def test_defaults() -> None:
    standard = rate()
    assert (standard.exemption_reason, standard.notice, standard.preset, standard.hidden) == (
        "",
        "",
        None,
        False,
    )


@pytest.mark.parametrize("percent", ["0", "0.01", "99.99"])
def test_percentages_from_zero_to_below_hundred(percent: str) -> None:
    assert RateValue(date(2024, 1, 1), Decimal(percent)).percent == Decimal(percent)


@pytest.mark.parametrize(
    ("percent", "message"),
    [
        ("-0.01", "the percentage must be from 0 to below 100"),
        ("100", "the percentage must be from 0 to below 100"),
        ("7.775", "the percentage has at most two decimal places"),
    ],
)
def test_refused_percentages(percent: str, message: str) -> None:
    with pytest.raises(ValidationError) as error:
        RateValue(date(2024, 1, 1), Decimal(percent))
    assert error.value.details == {"percent": message}


def test_dated_values() -> None:
    many = tuple(value(date(2000 + year, 1, 1), "8") for year in range(MAX_RATE_VALUES))
    assert len(rate(values=many).values) == MAX_RATE_VALUES
    message = f"a rate needs 1 to {MAX_RATE_VALUES} dated percentages"
    refused("values", message, values=())
    refused("values", message, values=(*many, value(date(2100, 1, 1), "8")))
    refused(
        "values",
        "the dates of the percentages must differ",
        values=(value(date(2024, 1, 1), "8"), value(date(2024, 1, 1), "9")),
    )
    refused(
        "values",
        "the dates of the percentages must differ",
        values=(value(date(2024, 1, 1), "8"), value(date(2018, 1, 1), "9")),
    )


def test_taxable_rates_need_a_percentage() -> None:
    refused(
        "category",
        "a taxable rate (S) needs a percentage above 0",
        "rate_standard_needs_percent",
        values=(value(date(2018, 1, 1), "7.7"), value(date(2024, 1, 1), "0")),
    )


@pytest.mark.parametrize("category", [RateCategory.ZERO, RateCategory.EXEMPT])
def test_zero_and_exempt_rates_are_zero(category: RateCategory) -> None:
    refused(
        "category",
        "zero-rated (Z) and exempt (E) rates must be 0 %",
        "rate_zero_needs_zero",
        category=category,
        exemption_reason="§ 4 UStG",
        values=(value(date(2018, 1, 1), "0"), value(date(2024, 1, 1), "0.01")),
    )


def test_exempt_rates_name_the_reason() -> None:
    zero = (value(date(2024, 1, 1), "0"),)
    refused(
        "exemption_reason",
        "an exempt rate (E) needs the reason for the exemption",
        "rate_exempt_needs_reason",
        category=RateCategory.EXEMPT,
        values=zero,
    )
    exempt = rate(category=RateCategory.EXEMPT, values=zero, exemption_reason="§ 4 Nr. 14 UStG")
    assert exempt.percent_on(date(2025, 1, 1)) == Decimal(0)
    # Zero-rated supplies need no reason.
    assert rate(category=RateCategory.ZERO, values=zero).category is RateCategory.ZERO


@pytest.mark.parametrize(
    ("category", "kind"),
    [
        (RateCategory.STANDARD, TaxCategory.STANDARD),
        (RateCategory.ZERO, TaxCategory.ZERO),
        (RateCategory.EXEMPT, TaxCategory.EXEMPT),
    ],
)
def test_the_kind_of_lines_with_a_rate(category: RateCategory, kind: TaxCategory) -> None:
    percent = "8.1" if category is RateCategory.STANDARD else "0"
    taxed = rate(
        category=category, values=(value(date(2024, 1, 1), percent),), exemption_reason="x"
    )
    assert taxed.kind is kind


def test_issued_documents_keep_the_words_of_a_rate() -> None:
    average = rate(
        name="Landwirtschaft § 24",
        notice="Durchschnittssatz § 24 UStG",
        exemption_reason="",
        preset="de_24_other",
        hidden=True,
    )
    assert average.frozen() == FrozenRate(
        id=average.id,
        name="Landwirtschaft § 24",
        category=RateCategory.STANDARD,
        notice="Durchschnittssatz § 24 UStG",
        exemption_reason="",
    )
    exempt = rate(
        category=RateCategory.EXEMPT,
        values=(value(date(2024, 1, 1), "0"),),
        exemption_reason="§ 4 Nr. 14 UStG",
    )
    assert exempt.frozen().exemption_reason == "§ 4 Nr. 14 UStG"
    assert exempt.frozen().category is RateCategory.EXEMPT
    bare = FrozenRate(id=exempt.id, name="x", category=RateCategory.ZERO)
    assert (bare.notice, bare.exemption_reason) == ("", "")
