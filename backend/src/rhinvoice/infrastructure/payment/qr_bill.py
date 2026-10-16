"""Swiss QR-bill payment part (Switzerland and Liechtenstein), via the qrbill library.

Rules (SIX, Swiss Implementation Guidelines QR-bill 2.3):
- Accounts are Swiss or Liechtenstein IBANs; currency CHF or EUR.
- A QR-IBAN requires a QR reference (QRR), a normal IBAN allows a creditor
  reference (SCOR, ISO 11649) or none.
- Addresses are structured (street, number, postal code, town, country); the
  debtor may be left empty (the payer fills it in).
- Only the characters of chapter 4.1.1 are allowed in the QR code.
"""

from __future__ import annotations

import io
import logging
import unicodedata
from typing import TYPE_CHECKING, Literal

from qrbill import QRBill

from rhinvoice.domain.country.profile import PaymentCode
from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.payment.reference import creditor_reference, qr_reference
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency

if TYPE_CHECKING:
    from datetime import date

    from rhinvoice.application.document.printing import PrintModel
    from rhinvoice.domain.company.bank_account import BankAccount
    from rhinvoice.domain.shared.address import Address

logger = logging.getLogger(__name__)

QR_BILL_CURRENCIES = frozenset({Currency.CHF, Currency.EUR})
QR_BILL_IBAN_COUNTRIES = frozenset({"CH", "LI"})
QR_BILL_MAX_NAME = 70
_CURRENCIES: dict[Currency, Literal["CHF", "EUR"]] = {Currency.CHF: "CHF", Currency.EUR: "EUR"}
_LANGUAGES: dict[Language, Literal["de", "en", "fr", "it"]] = {
    Language.DE: "de",
    Language.EN: "en",
    Language.FR: "fr",
    Language.IT: "it",
}
"""The payment part is printed in the document's language (qrbill knows all four)."""
# Chapter 4.1.1: Basic Latin, Latin-1 Supplement and Latin Extended-A ...
_CHARACTER_RANGES = ((0x20, 0x7E), (0xA0, 0xFF), (0x100, 0x17F))
# ... plus Ș ș Ț ț and €.
_EXTRA_CHARACTERS = frozenset({"\u0218", "\u0219", "\u021a", "\u021b", "\u20ac"})


def _allowed(character: str) -> bool:
    code = ord(character)
    return character in _EXTRA_CHARACTERS or any(
        first <= code <= last for first, last in _CHARACTER_RANGES
    )


def swiss_text(text: str) -> str:
    """Limit text to the QR-bill character set, on one line.

    Other characters become their base letters where possible (e.g. "ǅ" → "Dž")
    and are dropped otherwise.
    """
    kept: list[str] = []
    for character in text:
        if _allowed(character) or character.isspace():
            kept.append(character)
            continue
        for part in unicodedata.normalize("NFC", unicodedata.normalize("NFKD", character)):
            if _allowed(part):
                kept.append(part)
            else:
                kept.extend(base for base in unicodedata.normalize("NFKD", part) if _allowed(base))
    return " ".join("".join(kept).split())


def _address(name: str, address: Address) -> dict[str, str]:
    # The other fields share the limits of the QR-bill (domain/shared/address.py);
    # names of persons (first and last name) can be longer. The supplement (c/o,
    # P.O. box) has no field in a structured address.
    return {
        "name": swiss_text(name)[:QR_BILL_MAX_NAME].strip(),
        "street": swiss_text(address.street),
        "house_num": swiss_text(address.house_number),
        "pcode": swiss_text(address.postal_code),
        "city": swiss_text(address.city),
        "country": address.country.value,
    }


def qr_bill_account(model: PrintModel) -> BankAccount | None:
    """Return the account of the payment part, or None when the document gets none."""
    account = model.bank_account
    if (
        model.view.document.type is not DocumentType.INVOICE
        or PaymentCode.SWISS_QR_BILL not in profile_of(model.company.country).payment_codes
        or account is None
        or account.currency not in QR_BILL_CURRENCIES
        or account.currency is not model.payable.currency
        or account.iban.country not in QR_BILL_IBAN_COUNTRIES
        or model.payable.amount <= 0
    ):
        return None
    return account


def payment_reference(
    account: BankAccount, number: str, issue_date: date
) -> tuple[str, str | None]:
    """Choose the IBAN to pay to and the reference.

    A QR-IBAN with a QR reference when the account has one; otherwise the IBAN
    with a creditor reference, or without a reference when the number has too
    many characters for one (numbers have up to 30).
    """
    if account.qr_iban is not None:
        try:
            return account.qr_iban.value, qr_reference(number, issue_date)
        except ValidationError:
            logger.warning("number %s gives no QR reference, paying to the IBAN", number)
    # Numbers too long for a QR reference are too long for a creditor reference too.
    try:
        return account.iban.value, creditor_reference(number)
    except ValidationError:
        return account.iban.value, None


def swiss_qr_bill(model: PrintModel, remittance: str) -> str | None:
    """Render the payment part of an issued invoice as SVG, or None when it has none.

    Drafts get none: a payable code with a reference that changes when issuing
    could not be matched to the invoice.
    """
    account = qr_bill_account(model)
    document = model.view.document
    if account is None or document.number is None:
        return None
    iban, reference = payment_reference(account, document.number, model.issue_date)
    total = model.payable
    # The creditor is the account holder (SIX IG 3.2.4), e.g. the owner of a sole
    # proprietorship rather than its trade name; the EPC QR code names the same.
    creditor = _address(account.holder, model.company.address)
    recipient = model.recipient
    debtors = (
        [None] if recipient is None else [_address(recipient.display_name, recipient.address), None]
    )
    for debtor in debtors:
        try:
            bill = QRBill(
                account=iban,
                creditor=creditor,
                amount=f"{total.amount:.2f}",
                currency=_CURRENCIES[total.currency],
                debtor=debtor,
                reference_number=reference,
                additional_information=swiss_text(remittance),
                language=_LANGUAGES[document.content.language],
            )
            svg = io.StringIO()
            bill.as_svg(svg)
        except ValueError:
            # Data the QR-bill does not accept: try again without the debtor (the
            # payer fills it in), then leave the payment part out.
            logger.warning("QR-bill of document %s refused its data", document.id, exc_info=True)
            continue
        # Inline in the page: without the XML declaration.
        return svg.getvalue().split("?>", 1)[-1].strip()
    return None
