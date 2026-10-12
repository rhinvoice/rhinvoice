from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rhinvoice.domain.numbering.sequence import (
    NumberSequence,
    SequenceKind,
    format_number,
    validate_pattern,
)
from rhinvoice.domain.shared.errors import ValidationError


def test_format_number_placeholders() -> None:
    on = date(2026, 3, 9)
    assert format_number("R{YYYY}{NNNN}", 12, on) == "R20260012"
    assert format_number("{YY}-{MM}/{NNN}", 7, on) == "26-03/007"
    assert format_number("{N}", 12345, on) == "12345"
    assert format_number("{YY}{NN}", 5, date(2009, 1, 1)) == "0905"


def test_default_sequences() -> None:
    for kind in SequenceKind:
        assert NumberSequence.default(kind).kind is kind
    invoice = NumberSequence.default(SequenceKind.INVOICE)
    assert (invoice.pattern, invoice.start_value, invoice.yearly_reset) == (
        "R{YYYY}{NNNN}",
        1,
        True,
    )
    customer = NumberSequence.default(SequenceKind.CUSTOMER)
    assert customer.preview(date(2026, 1, 1)) == "1001"
    assert NumberSequence.default(SequenceKind.QUOTE).pattern == "A{YYYY}{NNNN}"
    assert NumberSequence.default(SequenceKind.CANCELLATION).pattern == "S{YYYY}{NNNN}"
    assert NumberSequence.default(SequenceKind.ARTICLE).start_value == 1


def test_allocation_counts_up_and_resets_each_year() -> None:
    sequence = NumberSequence.default(SequenceKind.INVOICE)
    first, sequence = sequence.allocate(date(2026, 12, 31))
    second, sequence = sequence.allocate(date(2026, 12, 31))
    assert (first, second) == ("R20260001", "R20260002")
    assert sequence.last_year == 2026
    assert sequence.preview(date(2027, 1, 1)) == "R20270001"
    third, sequence = sequence.allocate(date(2027, 1, 1))
    assert third == "R20270001"
    assert sequence.next_value == 2


def test_no_reset_without_yearly_reset() -> None:
    sequence = NumberSequence.default(SequenceKind.CUSTOMER)
    _, sequence = sequence.allocate(date(2026, 12, 31))
    number, _ = sequence.allocate(date(2027, 1, 1))
    assert number == "1002"


def test_next_counter_reflects_the_yearly_reset() -> None:
    _, sequence = NumberSequence.default(SequenceKind.INVOICE).allocate(date(2026, 6, 1))
    assert sequence.next_counter(date(2026, 6, 2)) == 2
    assert sequence.next_counter(date(2027, 1, 1)) == 1


def test_reconfigured_next_value_applies_in_the_year_of_the_change() -> None:
    _, sequence = NumberSequence.default(SequenceKind.INVOICE).allocate(date(2025, 6, 1))
    sequence = sequence.reconfigure(
        pattern="R{YYYY}{NNNN}",
        start_value=1,
        yearly_reset=True,
        next_value=50,
        on=date(2026, 3, 1),
    )
    assert sequence.last_year == 2026
    number, sequence = sequence.allocate(date(2026, 3, 2))
    assert number == "R20260050"
    assert sequence.preview(date(2027, 1, 1)) == "R20270001"


def test_reconfiguring_in_december_still_resets_in_january() -> None:
    sequence = NumberSequence.default(SequenceKind.INVOICE).reconfigure(
        pattern="R{YYYY}{NNNN}",
        start_value=1,
        yearly_reset=True,
        next_value=57,
        on=date(2026, 12, 20),
    )
    assert sequence.allocate(date(2027, 1, 4))[0] == "R20270001"


def test_numbers_must_fit_the_column() -> None:
    long = NumberSequence.default(SequenceKind.CUSTOMER).reconfigure(
        pattern="KUNDE-{YYYY}-{NNNNNNNNNNNN}",
        start_value=1,
        yearly_reset=False,
        next_value=1,
        on=date(2026, 1, 1),
    )
    with pytest.raises(ValidationError) as error:
        long.preview(date(2026, 1, 1))
    assert error.value.details == {
        "pattern": "numbers of this sequence must have at most 20 characters"
    }
    with pytest.raises(ValidationError):
        long.allocate(date(2026, 1, 1))
    longest = NumberSequence.default(SequenceKind.CUSTOMER).reconfigure(
        pattern="KUNDE-{YYYY}-{NNNNNNNNN}",
        start_value=1,
        yearly_reset=False,
        next_value=1,
        on=date(2026, 1, 1),
    )
    assert longest.preview(date(2026, 1, 1)) == "KUNDE-2026-000000001"


def test_an_exhausted_sequence_is_reported() -> None:
    last = NumberSequence.default(SequenceKind.ARTICLE).reconfigure(
        pattern="{N}",
        start_value=1,
        yearly_reset=False,
        next_value=10**12 - 2,
        on=date(2026, 1, 1),
    )
    number, last = last.allocate(date(2026, 1, 1))
    assert number == str(10**12 - 2)
    with pytest.raises(ValidationError) as error:
        last.allocate(date(2026, 1, 1))
    assert error.value.details == {
        "next_value": "the number sequence is exhausted, please reconfigure it"
    }


def test_reconfigure_continues_after_previous_program() -> None:
    sequence = NumberSequence.default(SequenceKind.INVOICE).reconfigure(
        pattern="RE-{YY}-{NNNNN}",
        start_value=1,
        yearly_reset=True,
        next_value=345,
        on=date(2026, 1, 1),
    )
    assert sequence.preview(date(2026, 5, 1)) == "RE-26-00345"
    assert (sequence.pattern, sequence.start_value, sequence.yearly_reset, sequence.next_value) == (
        "RE-{YY}-{NNNNN}",
        1,
        True,
        345,
    )
    plain = sequence.reconfigure(
        pattern="{NNN}", start_value=7, yearly_reset=False, next_value=9, on=date(2026, 1, 1)
    )
    assert (plain.start_value, plain.yearly_reset) == (7, False)


def test_sequence_validates_its_pattern_with_reset_flag() -> None:
    with pytest.raises(ValidationError):
        NumberSequence(
            kind=SequenceKind.INVOICE,
            pattern="{NNNN}",
            start_value=1,
            yearly_reset=True,
            next_value=1,
        )


@pytest.mark.parametrize(
    ("pattern", "reset", "message"),
    [
        ("", False, "pattern must have 1 to 40 characters"),
        ("{N}" + "x" * 38, False, "pattern must have 1 to 40 characters"),
        ("R{YYYY}", False, "pattern must contain exactly one counter such as {NNNN}"),
        ("{NN}{NNN}", False, "pattern must contain exactly one counter such as {NNNN}"),
        ("{DD}{NNN}", False, "unknown placeholder {DD}"),
        (
            "R {NNN}",
            False,
            "pattern may only contain letters, digits and - _ / . besides placeholders",
        ),
        (
            "{NNN} x",
            False,
            "pattern may only contain letters, digits and - _ / . besides placeholders",
        ),
        (
            "{YY}-{NNN} x{MM}",
            False,
            "pattern may only contain letters, digits and - _ / . besides placeholders",
        ),
        (
            "{NNNN}",
            True,
            "a yearly reset needs {YYYY} or {YY} in the pattern, otherwise numbers repeat",
        ),
    ],
)
def test_invalid_patterns(pattern: str, reset: bool, message: str) -> None:
    with pytest.raises(ValidationError) as error:
        validate_pattern(pattern, yearly_reset=reset)
    assert error.value.details == {"pattern": message}


def test_valid_patterns() -> None:
    validate_pattern("{N}" + "x" * 37, yearly_reset=False)
    validate_pattern("RE/{YY}.{MM}-{NNNN}_x", yearly_reset=True)


@pytest.mark.parametrize(
    ("field", "values", "message"),
    [
        ("start_value", {"start_value": 0}, "start value must be a positive number"),
        ("start_value", {"start_value": 10**12}, "start value must be a positive number"),
        ("next_value", {"next_value": 0}, "next value must be a positive number"),
        ("next_value", {"next_value": 10**12}, "next value must be a positive number"),
    ],
)
def test_counter_bounds(field: str, values: dict[str, int], message: str) -> None:
    arguments: dict[str, object] = {
        "kind": SequenceKind.INVOICE,
        "pattern": "{NNNN}",
        "start_value": 1,
        "yearly_reset": False,
        "next_value": 1,
        **values,
    }
    with pytest.raises(ValidationError) as error:
        NumberSequence(**arguments)  # type: ignore[arg-type]  # dynamic test values
    assert error.value.details == {field: message}
    assert NumberSequence(**{**arguments, field: 10**12 - 1}).pattern == "{NNNN}"  # type: ignore[arg-type]


@given(
    st.integers(min_value=1, max_value=500),
    st.dates(min_value=date(2000, 1, 1), max_value=date(2099, 12, 31)),
)
def test_allocated_numbers_are_unique_within_a_year(count: int, on: date) -> None:
    sequence = NumberSequence.default(SequenceKind.INVOICE)
    numbers: list[str] = []
    for _ in range(count):
        number, sequence = sequence.allocate(on)
        numbers.append(number)
    assert len(set(numbers)) == count
    assert numbers[0] == f"R{on.year}0001"
