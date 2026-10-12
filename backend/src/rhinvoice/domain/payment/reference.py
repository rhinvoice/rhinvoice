"""Payment references printed with payment codes and quoted by the payer.

- QR reference (QRR), Swiss QR-bill with a QR-IBAN: 27 digits, the last one a
  check digit computed with the recursive modulo 10 algorithm (SIX, Swiss
  Implementation Guidelines QR-bill, version 2.3, Annex B).
- Creditor reference (SCOR), ISO 11649: "RF", two check digits (ISO 7064
  MOD 97-10) and up to 21 letters or digits; usable with any IBAN.

Both are derived from the document number, so they are frozen with it.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.errors import ValidationError

if TYPE_CHECKING:
    from datetime import date

QR_REFERENCE_LENGTH = 27
CREDITOR_REFERENCE_MAX_PAYLOAD = 21
_RECURSIVE_MOD10 = (0, 9, 4, 6, 8, 2, 7, 1, 3, 5)
_ALPHANUMERIC = re.compile(r"[^0-9A-Z]")


def mod10_recursive(digits: str) -> int:
    """Check digit of the recursive modulo 10 algorithm."""
    carry = 0
    for digit in digits:
        carry = _RECURSIVE_MOD10[(carry + int(digit)) % 10]
    return (10 - carry) % 10


def qr_reference(number: str, issue_date: date) -> str:
    """Build the QR reference of an invoice: issue year and the digits of its number."""
    digits = "".join(character for character in number if character.isdigit())
    payload = f"{issue_date.year}{digits}"
    if len(payload) > QR_REFERENCE_LENGTH - 1:
        raise ValidationError(
            "number", "the document number has too many digits for a QR reference"
        )
    payload = payload.rjust(QR_REFERENCE_LENGTH - 1, "0")
    return payload + str(mod10_recursive(payload))


def is_qr_reference(value: str) -> bool:
    return (
        len(value) == QR_REFERENCE_LENGTH
        and value.isdigit()
        and mod10_recursive(value[:-1]) == int(value[-1])
    )


def _mod97(text: str) -> int:
    """ISO 7064 MOD 97-10 of letters and digits (A = 10 … Z = 35)."""
    return int("".join(str(int(character, 36)) for character in text)) % 97


def creditor_reference(number: str) -> str:
    """Build the ISO 11649 creditor reference of a document number, e.g. "RF15R20260042"."""
    payload = _ALPHANUMERIC.sub("", number.upper())
    if not payload or len(payload) > CREDITOR_REFERENCE_MAX_PAYLOAD:
        raise ValidationError(
            "number", "the document number does not fit a creditor reference (1-21 characters)"
        )
    check = 98 - _mod97(f"{payload}RF00")
    return f"RF{check:02d}{payload}"


def is_creditor_reference(value: str) -> bool:
    return (
        re.fullmatch(r"RF\d{2}[0-9A-Z]{1,21}", value) is not None
        and _mod97(value[4:] + value[:4]) == 1
    )
