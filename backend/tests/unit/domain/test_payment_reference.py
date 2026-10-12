from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rhinvoice.domain.payment.reference import (
    creditor_reference,
    is_creditor_reference,
    is_qr_reference,
    mod10_recursive,
    qr_reference,
)
from rhinvoice.domain.shared.errors import ValidationError
from tests.helpers import raises_exactly


def test_official_examples() -> None:
    # SIX, Swiss Implementation Guidelines QR-bill (example QR reference).
    assert is_qr_reference("210000000003139471430009017")
    assert mod10_recursive("21000000000313947143000901") == 7
    assert not is_qr_reference("210000000003139471430009018")
    assert not is_qr_reference("21000000000313947143000901")
    assert not is_qr_reference("2100000000031394714300090a7")
    # ISO 11649 example "RF18 5390 0754 7034".
    assert is_creditor_reference("RF18539007547034")
    assert not is_creditor_reference("RF19539007547034")
    assert not is_creditor_reference("RF18")
    assert not is_creditor_reference("rf18539007547034")
    assert creditor_reference("539007547034") == "RF18539007547034"


def test_qr_reference_from_the_number() -> None:
    # Issue year, then the digits of the number, padded to 26 digits plus the check digit.
    assert qr_reference("R20260042", date(2026, 3, 9)) == "000000000000002026202600426"
    assert qr_reference("RE-17", date(2025, 1, 1)) == "000000000000000000002025174"
    with raises_exactly(
        ValidationError, "the document number has too many digits for a QR reference"
    ):
        qr_reference("1" * 23, date(2026, 1, 1))
    assert len(qr_reference("1" * 22, date(2026, 1, 1))) == 27


def test_creditor_reference_from_the_number() -> None:
    assert creditor_reference("r-2026/0042") == creditor_reference("R20260042")
    assert creditor_reference("R20260042") == "RF15R20260042"
    with raises_exactly(
        ValidationError, "the document number does not fit a creditor reference (1-21 characters)"
    ):
        creditor_reference("---")
    with pytest.raises(ValidationError):
        creditor_reference("A" * 22)
    assert is_creditor_reference(creditor_reference("A" * 21))


@given(st.text(alphabet="0123456789", min_size=0, max_size=22), st.integers(2000, 2099))
def test_qr_references_are_always_valid(digits: str, year: int) -> None:
    assert is_qr_reference(qr_reference(f"R{digits}", date(year, 6, 1)))


@given(st.text(alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=21))
def test_creditor_references_are_always_valid(payload: str) -> None:
    reference = creditor_reference(payload)
    assert is_creditor_reference(reference)
    assert reference[4:] == payload
