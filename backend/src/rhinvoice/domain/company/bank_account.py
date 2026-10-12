"""Bank accounts printed on documents and used for payment codes."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.text import clean_text

if TYPE_CHECKING:
    from uuid import UUID

    from rhinvoice.domain.shared.iban import Bic, Iban
    from rhinvoice.domain.shared.money import Currency

MAX_BANK_NAME = 70
MAX_HOLDER = 70


@dataclass(frozen=True, slots=True)
class BankAccount:
    id: UUID
    currency: Currency
    bank_name: str
    holder: str
    iban: Iban
    qr_iban: Iban | None = None
    """Swiss/Liechtenstein QR-IBAN for QR-bills with QR reference (QRR)."""
    bic: Bic | None = None
    is_default: bool = False
    """Default account for documents in this currency."""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "bank_name",
            clean_text(self.bank_name, "bank_name", max_length=MAX_BANK_NAME, required=True),
        )
        object.__setattr__(
            self,
            "holder",
            clean_text(self.holder, "holder", max_length=MAX_HOLDER, required=True),
        )
        if self.iban.is_qr_iban:
            raise ValidationError(
                "iban",
                "this is a QR-IBAN; enter it as QR-IBAN and the regular IBAN here",
            )
        if self.qr_iban is not None:
            if not self.qr_iban.is_qr_iban:
                raise ValidationError(
                    "qr_iban",
                    "a QR-IBAN is a CH/LI IBAN with an institution id from 30000 to 31999",
                )
            if self.qr_iban.country != self.iban.country:
                raise ValidationError("qr_iban", "QR-IBAN and IBAN must be from the same country")

    def as_default(self, *, is_default: bool) -> BankAccount:
        return replace(self, is_default=is_default)
