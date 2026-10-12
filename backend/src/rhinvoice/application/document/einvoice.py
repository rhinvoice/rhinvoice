"""E-invoices: the invoice as structured data next to (or instead of) the PDF.

Two profiles of EN 16931 in the CII syntax (UN/CEFACT Cross Industry Invoice):

* ZUGFeRD / Factur-X, profile EN 16931: embedded in the PDF (PDF/A-3), so a
  single file serves people and accounting software. Accepted for B2B in
  Germany (§ 14 Abs. 1 UStG since 2025) and widely read in AT and CH.
* XRechnung: the German CIUS for the public sector, a plain XML file; it asks
  for more (buyer reference / Leitweg-ID, contact, electronic addresses).

Only issued invoices and cancellations are e-invoices; quotes and drafts are not.
See ADR 0013.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.shared.errors import InvalidStateError
from rhinvoice.domain.tax.treatment import TaxTreatment
from rhinvoice.domain.tax.vat_code import VatCode

if TYPE_CHECKING:
    from rhinvoice.application.document.printing import PrintModel
    from rhinvoice.domain.company.bank_account import BankAccount
    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.customer.customer import Customer
    from rhinvoice.domain.document.document import Document

E_INVOICE_TYPES = frozenset({DocumentType.INVOICE, DocumentType.CANCELLATION})


class EInvoiceProfile(StrEnum):
    EN16931 = "en16931"
    """ZUGFeRD / Factur-X EN 16931 (embedded in the PDF)."""
    XRECHNUNG = "xrechnung"
    """XRechnung 3.0 (CIUS of the German public sector)."""


class EInvoiceProblem(StrEnum):
    """Why a document cannot be written as an e-invoice of a profile."""

    SELLER_ID_MISSING = "seller_id_missing"
    """The seller needs a VAT ID, a UID or a commercial register entry (BR-CO-26)."""
    SELLER_VAT_ID_MISSING = "seller_vat_id_missing"
    """Reverse charge, intra-Community supplies and exports need the seller's VAT ID
    (BR-AE-02, BR-IC-02, BR-G-02)."""
    SELLER_TAX_ID_MISSING = "seller_tax_id_missing"
    """Taxed and exempt supplies need the VAT ID or tax number (BR-S-02, BR-E-02)."""
    BUYER_VAT_ID_MISSING = "buyer_vat_id_missing"
    """Reverse charge and intra-Community supplies need the buyer's VAT ID with country
    prefix (BR-AE-02, BR-IC-02)."""
    BUYER_REFERENCE_MISSING = "buyer_reference_missing"
    """XRechnung: the reference field carries the buyer reference / Leitweg-ID (BR-DE-15)."""
    SELLER_EMAIL_MISSING = "seller_email_missing"
    """XRechnung: the company's e-mail (contact and electronic address, BR-DE-7)."""
    SELLER_PHONE_MISSING = "seller_phone_missing"
    """XRechnung: the company's phone (contact, BR-DE-6)."""
    BUYER_EMAIL_MISSING = "buyer_email_missing"
    """XRechnung: the customer's e-mail (buyer electronic address BT-49, mandatory in 3.0)."""
    BANK_ACCOUNT_MISSING = "bank_account_missing"
    """XRechnung: payment instructions with an account, also for credit notes (BR-DE-1)."""


NOT_SUBJECT = "O"
"""UNCL5305 "Services outside scope of tax" (e-invoices only, not part of VatCode)."""
NEED_BUYER_VAT_ID = frozenset({VatCode.REVERSE_CHARGE.value, VatCode.INTRA_COMMUNITY.value})
NEED_SELLER_VAT_ID = NEED_BUYER_VAT_ID | {VatCode.EXPORT.value}
NEED_SELLER_TAX_ID = frozenset({VatCode.STANDARD.value, VatCode.ZERO.value, VatCode.EXEMPT.value})
SWISS_UID_PREFIX = "CHE"
SWISS_UID_LENGTH = 12
"""CHE and nine digits; a MWST/TVA/IVA suffix follows for VAT registered businesses."""
UID_SCHEME = "0183"
"""ISO 6523 ICD of the Swiss business identification number (UID)."""
_NOT_ALPHANUMERIC = re.compile(r"[^A-Z0-9]")
_COUNTRY_PREFIX = re.compile(r"[A-Z]{2}")


def is_e_invoice_type(document: Document) -> bool:
    """Invoices and cancellations (also as drafts); quotes never are."""
    return document.type in E_INVOICE_TYPES


def is_e_invoice(document: Document) -> bool:
    """Issued invoices and cancellations; quotes and drafts are no invoices yet."""
    return is_e_invoice_type(document) and not document.is_draft


def vat_id(raw: str) -> str | None:
    """Write a VAT number as EN 16931 wants it ("CHE-123.456.789 MWST" → "CHE123456789MWST").

    None when it has no country prefix (then it is a tax registration number).
    """
    compact = _NOT_ALPHANUMERIC.sub("", raw.upper())
    return compact if _COUNTRY_PREFIX.match(compact) else None


@dataclass(frozen=True, slots=True)
class SellerIds:
    vat_id: str | None
    """BT-31: only a VAT registration (no Swiss UID of a small business)."""
    tax_number: str | None
    """BT-32."""
    legal_id: str | None
    """BT-30: the Swiss UID, else the commercial register entry."""
    legal_scheme: str | None
    """ISO 6523 ICD of BT-30: 0183 for the Swiss UID."""
    legal_info: str | None
    """BT-33: the commercial register entry when BT-30 is the UID."""


def seller_ids(company: Company) -> SellerIds:
    """Sort the company's numbers into the identifiers of EN 16931."""
    raw = None if company.vat_number is None else company.vat_number.value
    register = company.commercial_register.strip() or None
    tax_number = company.tax_number.strip() or None
    if raw is None:
        return SellerIds(None, tax_number, register, None, None)
    compact = _NOT_ALPHANUMERIC.sub("", raw.upper())
    if compact.startswith(SWISS_UID_PREFIX):
        # The UID is the MWST number of a registered business, also when typed without
        # MWST/TVA/IVA; small businesses are not registered: their UID only names them.
        registered = len(compact) > SWISS_UID_LENGTH or not company.small_business
        uid = compact[:SWISS_UID_LENGTH]
        return SellerIds(compact if registered else None, tax_number, uid, UID_SCHEME, register)
    identifier = vat_id(raw)
    # A VAT number without country prefix is a tax registration (BT-32).
    return SellerIds(
        identifier, tax_number or (raw if identifier is None else None), register, None, None
    )


def not_subject(model: PrintModel) -> bool:
    """Tell whether a small business without VAT or tax number is outside VAT ("O")."""
    ids = seller_ids(model.company)
    return (
        model.view.document.content.treatment is TaxTreatment.SMALL_BUSINESS
        and ids.vat_id is None
        and ids.tax_number is None
    )


def vat_category(model: PrintModel, code: VatCode) -> str:
    """Name the VAT category of a group in the e-invoice (UNCL5305)."""
    return NOT_SUBJECT if not_subject(model) else code.value


def payment_account(model: PrintModel) -> BankAccount | None:
    """Name the account of the payment instructions; a credit note uses the invoice's."""
    if model.view.document.type is DocumentType.CANCELLATION:
        return model.cancelled_account
    return model.bank_account


def customer_of(model: PrintModel) -> Customer:
    customer = model.recipient
    if customer is None:
        msg = "an e-invoice needs a customer"
        raise InvalidStateError(msg)
    return customer


def _xrechnung_problems(model: PrintModel) -> list[EInvoiceProblem]:
    """Name what XRechnung asks for beyond EN 16931 (BR-DE-1, -2, -5 to -7, -15, BT-49)."""
    company = model.company
    found: list[EInvoiceProblem] = []
    if not model.view.document.content.reference.strip():
        found.append(EInvoiceProblem.BUYER_REFERENCE_MISSING)
    if company.email is None:
        found.append(EInvoiceProblem.SELLER_EMAIL_MISSING)
    if not company.phone.strip():
        found.append(EInvoiceProblem.SELLER_PHONE_MISSING)
    if customer_of(model).email is None:
        found.append(EInvoiceProblem.BUYER_EMAIL_MISSING)
    # Payment instructions also for credit notes (BR-DE-1 applies to both).
    if payment_account(model) is None:
        found.append(EInvoiceProblem.BANK_ACCOUNT_MISSING)
    return found


def problems(model: PrintModel, profile: EInvoiceProfile) -> tuple[EInvoiceProblem, ...]:
    """Name what keeps the document from being a valid e-invoice of the profile."""
    customer = customer_of(model)
    categories = {vat_category(model, group.vat_code) for group in model.view.totals.groups}
    ids = seller_ids(model.company)
    found: list[EInvoiceProblem] = []
    if ids.vat_id is None and ids.legal_id is None:
        found.append(EInvoiceProblem.SELLER_ID_MISSING)
    if categories & NEED_SELLER_VAT_ID and ids.vat_id is None:
        found.append(EInvoiceProblem.SELLER_VAT_ID_MISSING)
    if categories & NEED_SELLER_TAX_ID and ids.vat_id is None and ids.tax_number is None:
        found.append(EInvoiceProblem.SELLER_TAX_ID_MISSING)
    buyer_vat = customer.vat_number
    # Only a VAT number with country prefix identifies the buyer (BR-AE-02).
    if categories & NEED_BUYER_VAT_ID and (buyer_vat is None or vat_id(buyer_vat.value) is None):
        found.append(EInvoiceProblem.BUYER_VAT_ID_MISSING)
    if profile is EInvoiceProfile.XRECHNUNG:
        found.extend(_xrechnung_problems(model))
    return tuple(found)


class EInvoiceWriter(Protocol):
    def xml(self, model: PrintModel, profile: EInvoiceProfile) -> bytes:
        """Write the e-invoice (CII XML); only for documents without problems."""
        ...
