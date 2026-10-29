"""Bank accounts printed on documents and used for payment codes.

An account usually belongs to the company. A third party's account (e.g. a
financial service provider that collects the payment) names its holder and
their address, which the payment codes and the e-invoice use as payee (ADR 0037).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.text import clean_text

if TYPE_CHECKING:
    from collections.abc import Iterable
    from uuid import UUID

    from rhinvoice.domain.shared.address import Address
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
    third_party: bool = False
    """The account belongs to someone else, who collects the payment (never guessed)."""
    holder_address: Address | None = None
    """The third party's address; own accounts have the company's (None here)."""

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
        if not self.third_party:
            object.__setattr__(self, "holder_address", None)
        elif self.holder_address is None:
            raise ValidationError(
                "holder_address",
                "a third party's account needs the holder's address",
                code="holder_address_missing",
            )

    def as_default(self, *, is_default: bool) -> BankAccount:
        return replace(self, is_default=is_default)

    def creditor_address(self, company_address: Address) -> Address:
        """Return the address of whoever is paid: the third party's, else the company's."""
        return company_address if self.holder_address is None else self.holder_address


def paying_account(
    accounts: Iterable[BankAccount], currency: Currency, chosen: UUID | None
) -> BankAccount | None:
    """Find the account a document in ``currency`` is paid to.

    The chosen one while it exists in that currency, otherwise (no choice, or the
    account was deleted since) the default account of the currency.
    """
    candidates = [account for account in accounts if account.currency is currency]
    found = next((account for account in candidates if account.id == chosen), None)
    if found is not None:
        return found
    return next((account for account in candidates if account.is_default), None)
