import operator
from collections.abc import Callable
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rhinvoice.domain.shared.errors import CurrencyMismatchError, ValidationError
from rhinvoice.domain.shared.money import Currency, Money, parse_decimal, round_half_up
from tests.helpers import raises_exactly

amounts = st.decimals(min_value=-(10**9), max_value=10**9, places=4, allow_nan=False)


def chf(value: str) -> Money:
    return Money.of(value, Currency.CHF)


def test_currency_minor_units() -> None:
    assert Currency.CHF.minor_units == 2
    assert Currency.EUR.minor_step == Decimal("0.01")


def test_parse_decimal_accepts_strings_ints_and_decimals() -> None:
    assert parse_decimal("1.50", "x") == Decimal("1.50")
    assert parse_decimal(3, "x") == Decimal(3)
    assert parse_decimal(Decimal("2.5"), "x") == Decimal("2.5")


@pytest.mark.parametrize("value", ["abc", "NaN", "Infinity", ""])
def test_parse_decimal_rejects_invalid_input(value: str) -> None:
    with pytest.raises(ValidationError) as error:
        parse_decimal(value, "quantity")
    assert error.value.field == "quantity"
    assert error.value.details == {"quantity": f"'{value}' is not a valid number"}


@pytest.mark.parametrize(
    ("value", "step", "expected"),
    [
        ("1.005", "0.01", "1.01"),
        ("1.004", "0.01", "1.00"),
        ("-1.005", "0.01", "-1.01"),
        ("1.025", "0.05", "1.05"),
        ("1.024", "0.05", "1.00"),
        ("1.075", "0.05", "1.10"),
        ("1.07", "0.05", "1.05"),
        ("2.5", "1", "3"),
    ],
)
def test_round_half_up(value: str, step: str, expected: str) -> None:
    result = round_half_up(Decimal(value), Decimal(step))
    assert result == Decimal(expected)
    assert str(result) == expected


@pytest.mark.parametrize("step", ["0", "-0.05"])
def test_round_half_up_rejects_non_positive_step(step: str) -> None:
    with pytest.raises(ValidationError) as error:
        round_half_up(Decimal(1), Decimal(step))
    assert error.value.details == {"step": "rounding step must be positive"}


def test_money_rejects_non_finite_amounts() -> None:
    with pytest.raises(ValidationError) as error:
        Money(Decimal("NaN"), Currency.CHF)
    assert error.value.details == {"amount": "amount must be finite"}


def test_money_of_reports_amount_field() -> None:
    with pytest.raises(ValidationError) as error:
        Money.of("x", Currency.CHF)
    assert error.value.field == "amount"


def test_money_constructors() -> None:
    assert Money.zero(Currency.EUR) == Money(Decimal(0), Currency.EUR)
    assert Money.from_minor(12345, Currency.CHF) == chf("123.45")
    assert chf("123.454").to_minor() == 12345
    assert chf("-0.005").to_minor() == -1


def test_money_arithmetic() -> None:
    assert chf("1.10") + chf("2.20") == chf("3.30")
    assert chf("1.10") - chf("2.20") == chf("-1.10")
    assert chf("1.10") * 3 == chf("3.30")
    assert 3 * chf("1.10") == chf("3.30")
    assert -chf("1.10") == chf("-1.10")
    assert chf("200").percent(Decimal("8.1")) == chf("16.2")


def test_money_comparisons() -> None:
    assert chf("1") < chf("2")
    assert not chf("2") < chf("2")
    assert chf("2") <= chf("2")
    assert not chf("3") <= chf("2")
    assert chf("3") > chf("2")
    assert not chf("2") > chf("2")
    assert chf("2") >= chf("2")
    assert not chf("1") >= chf("2")


def test_money_predicates() -> None:
    assert Money.zero(Currency.CHF).is_zero
    assert not chf("0.01").is_zero
    assert chf("-0.01").is_negative
    assert not chf("0").is_negative


@pytest.mark.parametrize(
    "operation",
    [operator.add, operator.sub, operator.lt, operator.le, operator.gt, operator.ge],
)
def test_money_rejects_mixed_currencies(operation: Callable[[Money, Money], object]) -> None:
    with raises_exactly(CurrencyMismatchError, "cannot combine CHF with EUR"):
        operation(chf("1"), Money.of("1", Currency.EUR))


def test_money_rounding_and_str() -> None:
    assert chf("1.005").round_to_minor() == chf("1.01")
    assert chf("1.024").round_to_step(Decimal("0.05")) == chf("1.00")
    assert str(chf("1234.5")) == "CHF 1234.50"


@given(amounts, amounts)
def test_addition_is_commutative_and_subtraction_inverts(a: Decimal, b: Decimal) -> None:
    x, y = Money(a, Currency.CHF), Money(b, Currency.CHF)
    assert x + y == y + x
    assert (x + y) - y == x


@given(amounts)
def test_rounding_to_minor_is_idempotent_and_close(a: Decimal) -> None:
    rounded = Money(a, Currency.EUR).round_to_minor()
    assert rounded.round_to_minor() == rounded
    assert abs(rounded.amount - a) <= Decimal("0.005")


@given(amounts)
def test_rounding_to_five_rappen_yields_multiples_of_five(a: Decimal) -> None:
    rounded = round_half_up(a, Decimal("0.05"))
    assert (rounded * 100) % 5 == 0
    assert abs(rounded - a) <= Decimal("0.025")


@given(amounts)
def test_rounding_is_symmetric_around_zero(a: Decimal) -> None:
    """Cancellation invoices negate amounts; rounding must not depend on the sign."""
    assert round_half_up(-a, Decimal("0.01")) == -round_half_up(a, Decimal("0.01"))
    assert round_half_up(-a, Decimal("0.05")) == -round_half_up(a, Decimal("0.05"))


@given(st.integers(min_value=-(10**15), max_value=10**15))
def test_minor_units_round_trip(minor: int) -> None:
    assert Money.from_minor(minor, Currency.CHF).to_minor() == minor


@given(amounts, amounts, st.integers(min_value=-1000, max_value=1000))
def test_multiplication_distributes_over_addition(a: Decimal, b: Decimal, factor: int) -> None:
    x, y = Money(a, Currency.EUR), Money(b, Currency.EUR)
    assert (x + y) * factor == x * factor + y * factor


@given(amounts, st.decimals(min_value=0, max_value=100, places=2, allow_nan=False))
def test_percent_is_proportional(a: Decimal, rate: Decimal) -> None:
    money = Money(a, Currency.CHF)
    assert money.percent(rate) + money.percent(100 - rate) == money


def test_rounding_handles_large_amounts_exactly() -> None:
    huge = Decimal("123456789012345678901234567890.125")
    assert round_half_up(huge, Decimal("0.01")) == Decimal("123456789012345678901234567890.13")
