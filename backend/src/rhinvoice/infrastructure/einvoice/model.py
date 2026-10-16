"""An issued document in the terms of EN 16931 (business terms BT-…, groups BG-…).

The printed document stays the reference: every amount here is one of its
amounts, so the e-invoice and the PDF never disagree. Three translations are
needed on the way:

* Cancellations are credit notes (type 381) with positive amounts that refer
  to the cancelled invoice (BG-3); they are stored with negated quantities.
* Gross prices (B2C) become net amounts, the only ones EN 16931 knows. The net
  of each VAT group is the printed one; its lines share it in proportion.
* Small businesses without any tax number (CH/LI, not registered for VAT)
  are outside the scope of VAT ("O"); German and Austrian small businesses
  are exempt ("E") and state their tax number.

See ADR 0013.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from rhinvoice.application.document.einvoice import (
    NOT_SUBJECT,
    EInvoiceProfile,
    customer_of,
    not_subject,
    payment_account,
    seller_ids,
    vat_category,
    vat_id,
)
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import HUNDRED, LineKind, PriceMode
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency, round_half_up
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.vat_code import VatCode, vat_code
from rhinvoice.infrastructure.payment.qr_bill import payment_reference, qr_bill_account
from rhinvoice.infrastructure.rendering.labels import LABELS

if TYPE_CHECKING:
    from datetime import date
    from uuid import UUID

    from rhinvoice.application.document.printing import PrintModel
    from rhinvoice.domain.document.calculation import LineAmount, TaxGroup
    from rhinvoice.domain.document.lines import DocumentLine
    from rhinvoice.domain.shared.address import Address

INVOICE = "380"
CREDIT_NOTE = "381"
SPECIFICATIONS = {
    EInvoiceProfile.EN16931: "urn:cen.eu:en16931:2017",
    EInvoiceProfile.XRECHNUNG: (
        "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
    ),
}
BUSINESS_PROCESS = "urn:fdc:peppol.eu:2017:poacc:billing:01.0"
"""BT-23, the usual process of XRechnung (Peppol billing)."""
SEPA_CREDIT_TRANSFER = "58"
CREDIT_TRANSFER = "30"
DISCOUNT_REASON_CODE = "95"
"""UNCL5189 "Discount"."""
PRICE_STEP = Decimal("0.0001")
DEFAULT_UNIT = "C62"
"""UN/ECE Rec 20 "one", for lines without a unit."""
EXEMPTION_CODES = {
    VatCode.REVERSE_CHARGE.value: "VATEX-EU-AE",
    VatCode.EXPORT.value: "VATEX-EU-G",
    VatCode.INTRA_COMMUNITY.value: "VATEX-EU-IC",
    NOT_SUBJECT: "VATEX-EU-O",
}
EXEMPT_CATEGORIES = frozenset({VatCode.EXEMPT.value, *EXEMPTION_CODES})
FALLBACK_EXEMPTION = {
    Language.DE: "Steuerbefreite Leistung",
    Language.EN: "Exempt supply",
    Language.FR: "Prestation exonérée",
    Language.IT: "Prestazione esente",
}
"""The exemption reason (BT-120) when the document prints no notice."""


@dataclass(frozen=True, slots=True)
class Party:
    name: str
    """BT-27 / BT-44."""
    address: Address
    vat_id: str | None = None
    """BT-31 / BT-48, with the country prefix, without separators."""
    tax_number: str | None = None
    """BT-32 (seller only): a tax number, or a VAT number without country prefix."""
    legal_id: str | None = None
    """BT-30."""
    legal_scheme: str | None = None
    legal_info: str | None = None
    """BT-33."""
    email: str | None = None
    """BT-34 / BT-49 electronic address and BT-43 contact e-mail."""
    phone: str | None = None
    """BT-42."""
    contact: str | None = None
    """BT-41 / BT-56 contact point."""


@dataclass(frozen=True, slots=True)
class Line:
    position: int
    """BT-126."""
    name: str
    """BT-153."""
    description: str
    """BT-154."""
    quantity: Decimal
    """BT-129."""
    unit: str
    """BT-130."""
    net_price: Decimal
    """BT-146, never negative (BR-27): unit prices are not."""
    allowance: Decimal | None
    """BT-136: the line discount (negative on credit lines)."""
    discount: bool
    """The allowance is the line discount (reason code 95), else a rounding."""
    charge: Decimal | None
    """BT-141: the rounding of a net price derived from a gross price."""
    rounding: str
    """The reason text of rounding allowances and charges (BT-139, BT-144)."""
    net_amount: Decimal
    """BT-131."""
    category: str
    """BT-151."""
    rate: Decimal | None
    """BT-152; none for "O"."""


@dataclass(frozen=True, slots=True)
class Allowance:
    """BG-20, the document discount of one VAT group."""

    amount: Decimal
    category: str
    rate: Decimal | None
    reason: str


@dataclass(frozen=True, slots=True)
class VatBreakdown:
    """BG-23."""

    category: str
    rate: Decimal | None
    basis: Decimal
    tax: Decimal
    exemption_reason: str | None
    exemption_code: str | None


@dataclass(frozen=True, slots=True)
class Payment:
    """BG-16 / BG-17."""

    means: str
    iban: str
    holder: str
    bic: str | None
    remittance: str
    """BT-83: the QR or creditor reference of the payment part, else the number."""


@dataclass(frozen=True, slots=True)
class EInvoice:
    specification: str
    """BT-24."""
    business_process: str | None
    """BT-23."""
    type_code: str
    """BT-3."""
    number: str
    issue_date: date
    currency: Currency
    notes: tuple[str, ...]
    """BT-22."""
    buyer_reference: str | None
    """BT-10, the reference field (Leitweg-ID for German authorities)."""
    preceding: tuple[str, date] | None
    """BG-3, the cancelled invoice."""
    seller: Party
    buyer: Party
    deliver_to: tuple[str, Address] | None
    """BG-13: name (BT-70) and address (BG-15) where goods go; intra-Community supplies
    name the country of arrival (BR-IC-12)."""
    delivery_date: date
    """BT-72."""
    period: tuple[date, date] | None
    """BG-14."""
    payment: Payment | None
    due_date: date | None
    payment_terms: str | None
    """BT-20."""
    lines: tuple[Line, ...]
    allowances: tuple[Allowance, ...]
    breakdown: tuple[VatBreakdown, ...]
    line_total: Decimal
    """BT-106."""
    allowance_total: Decimal
    """BT-107."""
    tax_basis: Decimal
    """BT-109."""
    tax_total: Decimal
    """BT-110."""
    grand_total: Decimal
    """BT-112."""
    rounding: Decimal
    """BT-114, the Swiss 5-centime rounding."""
    due_payable: Decimal
    """BT-115."""


def _seller(model: PrintModel, profile: EInvoiceProfile) -> Party:
    company = model.company
    ids = seller_ids(company)
    email = None if company.email is None else company.email.value
    phone = company.phone.strip() or None
    has_contact = email is not None or phone is not None
    return Party(
        name=company.name,
        address=company.address,
        vat_id=None if not_subject(model) else ids.vat_id,
        tax_number=ids.tax_number,
        legal_id=ids.legal_id,
        legal_scheme=ids.legal_scheme,
        legal_info=ids.legal_info,
        email=email,
        phone=phone,
        contact=company.name if has_contact or profile is EInvoiceProfile.XRECHNUNG else None,
    )


def _buyer(model: PrintModel) -> Party:
    recipient = customer_of(model)
    vat_number = recipient.vat_number
    return Party(
        name=recipient.display_name,
        address=recipient.address,
        vat_id=(None if vat_number is None or not_subject(model) else vat_id(vat_number.value)),
        email=None if recipient.email is None else recipient.email.value,
        contact=recipient.contact_person.strip() or None,
    )


def _payment(model: PrintModel, profile: EInvoiceProfile) -> Payment | None:
    """BG-16: where to pay; credit notes only in XRechnung, which asks for it (BR-DE-1)."""
    document = model.view.document
    account = payment_account(model)
    credit_note = document.type is DocumentType.CANCELLATION
    if account is None or (credit_note and profile is EInvoiceProfile.EN16931):
        return None
    number = document.issued_number
    iban, reference = account.iban.value, None
    if qr_bill_account(model) is not None:
        iban, reference = payment_reference(account, number, model.issue_date)
    # QR-IBANs take no SEPA payments, also in euros.
    sepa = account.currency is Currency.EUR and iban == account.iban.value
    return Payment(
        means=SEPA_CREDIT_TRANSFER if sepa else CREDIT_TRANSFER,
        iban=iban,
        holder=account.holder,
        bic=None if account.bic is None else account.bic.value,
        remittance=reference or number,
    )


def _net_shares(
    amounts: list[Decimal], rate: Decimal, total: Decimal, step: Decimal
) -> list[Decimal]:
    """Split a group's net over its gross line amounts; the largest line takes the rest."""
    shares = [round_half_up(amount * HUNDRED / (HUNDRED + rate), step) for amount in amounts]
    largest = max(range(len(amounts)), key=lambda index: abs(amounts[index]))
    shares[largest] += total - sum(shares, Decimal(0))
    return shares


@dataclass(frozen=True, slots=True)
class _Group:
    group: TaxGroup
    lines: list[tuple[DocumentLine, LineAmount]]
    line_nets: list[Decimal]
    allowance: Decimal
    """The document discount, net."""


def _groups(model: PrintModel) -> list[_Group]:
    view = model.view
    content = view.document.content
    step = view.totals.currency.minor_step
    by_id = {line.id: line for line in content.lines}
    result: list[_Group] = []
    for group in view.totals.groups:
        members = [
            (by_id[amount.line_id], amount)
            for amount in view.totals.lines
            if (amount.vat_code, amount.tax_rate) == (group.vat_code, group.rate)
        ]
        amounts = [amount.amount.amount for _, amount in members]
        if content.price_mode is PriceMode.NET:
            result.append(_Group(group, members, amounts, group.discount.amount))
            continue
        gross = group.amount.amount
        net_before = gross - round_half_up(gross * group.rate / (HUNDRED + group.rate), step)
        result.append(
            _Group(
                group,
                members,
                _net_shares(amounts, group.rate, net_before, step),
                net_before - group.net.amount,
            )
        )
    return result


def _line(
    model: PrintModel,
    position: int,
    line: DocumentLine,
    net: Decimal,
    group: TaxGroup,
) -> Line:
    content = model.view.document.content
    sign = _sign(model)
    step = model.view.totals.currency.minor_step
    price = line.unit_price
    if content.price_mode is PriceMode.GROSS:
        price = round_half_up(price * HUNDRED / (HUNDRED + group.rate), PRICE_STEP).normalize()
    # Unit prices are never negative (DocumentLine), credits have a negative quantity.
    quantity = line.quantity * sign
    amount = net * sign
    # Quantity x price less the allowance plus the charge is the line amount, exactly:
    # the line discount is an allowance (negative on credit lines, and it takes the
    # rounding too); without discount, the cent that the net price of a gross price
    # leaves is a rounding allowance or charge.
    difference = round_half_up(quantity * price, step) - amount
    allowance = charge = None
    if line.discount_percent or difference > 0:
        allowance = difference or None
    elif difference:
        charge = -difference
    category = vat_category(model, group.vat_code)
    return Line(
        position=position,
        name=line.description,
        description=line.details,
        quantity=quantity,
        unit=DEFAULT_UNIT if line.unit is None else line.unit.code,
        net_price=price,
        allowance=allowance,
        discount=bool(line.discount_percent),
        charge=charge,
        rounding=LABELS[content.language]["rounding"],
        net_amount=amount,
        category=category,
        rate=None if category == NOT_SUBJECT else group.rate,
    )


def _sign(model: PrintModel) -> int:
    """Credit notes carry the cancellation's amounts as positive ones."""
    return -1 if model.view.document.type is DocumentType.CANCELLATION else 1


def _exemption(model: PrintModel, category: str) -> tuple[str | None, str | None]:
    """BT-120 and BT-121: the notices of the treatments that end up in ``category``."""
    if category not in EXEMPT_CATEGORIES:
        return None, None
    language = model.view.document.content.language
    notices = [
        text
        for treatment, text in model.view.notices
        if text and vat_category(model, vat_code(treatment, TaxCategory.STANDARD)) == category
    ]
    reason = " ".join(notices) or FALLBACK_EXEMPTION[language]
    return reason, EXEMPTION_CODES.get(category)


def _deliver_to(model: PrintModel, categories: set[str]) -> tuple[str, Address] | None:
    if VatCode.INTRA_COMMUNITY.value not in categories:
        return None
    customer = customer_of(model)
    return customer.display_name, customer.delivery_address or customer.address


def _dates(model: PrintModel) -> tuple[date, tuple[date, date] | None]:
    """BT-72 and BG-14: the day of supply, and the service period when it spans days."""
    content = model.view.document.content
    start, end = content.service_from, content.service_to
    if start is not None and end is not None and start != end:
        # The supply is complete at the end; an empty delivery breaks PEPPOL-EN16931-R008.
        return end, (start, end)
    return start or end or model.issue_date, None


def build(model: PrintModel, profile: EInvoiceProfile) -> EInvoice:
    """Translate an issued invoice or cancellation (see :func:`problems` first)."""
    view = model.view
    document = view.document
    content = document.content
    totals = view.totals
    cancellation = document.type is DocumentType.CANCELLATION
    sign = _sign(model)
    language: Language = content.language
    labels = LABELS[language]

    nets: dict[UUID, tuple[Decimal, TaxGroup]] = {}
    allowances: list[Allowance] = []
    breakdown: list[VatBreakdown] = []
    for item in _groups(model):
        group = item.group
        category = vat_category(model, group.vat_code)
        rate = None if category == NOT_SUBJECT else group.rate
        for (line, _), net in zip(item.lines, item.line_nets, strict=True):
            nets[line.id] = (net, group)
        if item.allowance:
            allowances.append(Allowance(item.allowance * sign, category, rate, labels["discount"]))
        reason, code = _exemption(model, category)
        breakdown.append(
            VatBreakdown(
                category, rate, group.net.amount * sign, group.tax.amount * sign, reason, code
            )
        )
    # In the order and with the numbers of the printed positions.
    items = [line for line in content.lines if line.kind is LineKind.ITEM]
    lines = [
        _line(model, position, line, *nets[line.id]) for position, line in enumerate(items, start=1)
    ]
    delivery_date, period = _dates(model)
    number, issued = model.cancelled_number, model.cancelled_issue_date
    preceding = (
        (number, issued) if cancellation and number is not None and issued is not None else None
    )
    return EInvoice(
        specification=SPECIFICATIONS[profile],
        business_process=BUSINESS_PROCESS if profile is EInvoiceProfile.XRECHNUNG else None,
        type_code=CREDIT_NOTE if cancellation else INVOICE,
        number=document.issued_number,
        issue_date=model.issue_date,
        currency=totals.currency,
        notes=tuple(note for note in (content.subject.strip(),) if note),
        buyer_reference=content.reference.strip() or None,
        preceding=preceding,
        seller=_seller(model, profile),
        buyer=_buyer(model),
        deliver_to=_deliver_to(model, {entry.category for entry in breakdown}),
        delivery_date=delivery_date,
        period=period,
        payment=_payment(model, profile),
        due_date=None if cancellation else model.due_date,
        payment_terms=(
            labels["cancels"].format(number=model.cancelled_number)
            if preceding is not None
            else None
        ),
        lines=tuple(lines),
        allowances=tuple(allowances),
        breakdown=tuple(breakdown),
        line_total=sum((line.net_amount for line in lines), Decimal(0)),
        allowance_total=sum((allowance.amount for allowance in allowances), Decimal(0)),
        tax_basis=totals.net.amount * sign,
        tax_total=totals.tax.amount * sign,
        grand_total=totals.gross.amount * sign,
        rounding=totals.rounding.amount * sign,
        due_payable=totals.total.amount * sign,
    )
