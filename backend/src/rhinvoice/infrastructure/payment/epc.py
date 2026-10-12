"""EPC QR code ("GiroCode", SEPA credit transfer) for invoices in euros.

Printed by companies in DE and AT, and by companies in CH and LI for customers in
the EU: banking apps there read the EPC QR code, but rarely the Swiss QR-bill,
which these invoices carry as well. Switzerland and Liechtenstein take part in
SEPA, so the payer's bank can transfer to the euro account.

European Payments Council, Quick Response Code guidelines (EPC069-12): IBAN,
name of the beneficiary (max. 70), amount up to EUR 999'999'999.99 and a
remittance text (max. 140), here the invoice number. The beneficiary is the
account holder (at most 70 characters, domain/company/bank_account.py): banks in
the EU compare it with the account (verification of payee). The remittance text
is short.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from segno import helpers

from rhinvoice.domain.country.profile import PaymentCode
from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.shared.money import Currency

if TYPE_CHECKING:
    from rhinvoice.application.document.printing import PrintModel
    from rhinvoice.domain.company.bank_account import BankAccount

EEA_OUTSIDE_EU = frozenset({"IS", "LI", "NO"})
NON_EEA_IBAN_COUNTRIES = frozenset({"CH"})
"""Outside the EEA the SEPA rulebook still asks for the beneficiary's BIC (EPC069-12 v002)."""
EPC_MAX_AMOUNT = Decimal("999999999.99")


def epc_account(model: PrintModel) -> BankAccount | None:
    """Return the account of the EPC QR code, or None when the document gets none."""
    account = model.bank_account
    total = model.payable
    if (
        model.view.document.type is not DocumentType.INVOICE
        or not _paid_from_the_eu(model)
        or account is None
        or total.currency is not Currency.EUR
        or account.currency is not Currency.EUR
        or (account.bic is None and account.iban.country in NON_EEA_IBAN_COUNTRIES)
        or not Decimal(0) < total.amount <= EPC_MAX_AMOUNT
    ):
        return None
    return account


def _paid_from_the_eu(model: PrintModel) -> bool:
    """Whether the payer banks in the EEA, where banking apps read the EPC QR code."""
    profile = profile_of(model.company.country)
    if PaymentCode.EPC in profile.payment_codes:
        return True
    recipient = model.recipient
    if PaymentCode.EPC_TO_EEA not in profile.payment_codes or recipient is None:
        return False
    country = recipient.address.country
    # Customers inside the VAT area (Liechtenstein for Swiss companies) pay the QR-bill.
    if country.value in profile.vat.area:
        return False
    return country.is_eu or country.value in EEA_OUTSIDE_EU


def epc_qr(model: PrintModel, remittance: str) -> str | None:
    """Render the EPC QR code of an issued invoice as SVG, or None when it has none.

    Drafts get none: their remittance text has no number yet.
    """
    account = epc_account(model)
    if account is None or model.view.document.number is None:
        return None
    code = helpers.make_epc_qr(
        name=account.holder,
        iban=account.iban.value,
        amount=model.payable.amount,
        text=remittance,
        bic=None if account.bic is None else account.bic.value,
    )
    return code.svg_inline(scale=4, border=0, omitsize=True)
