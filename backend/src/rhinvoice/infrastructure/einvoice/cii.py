"""EN 16931 in the CII syntax (UN/CEFACT Cross Industry Invoice D16B).

Element order follows the D16B schema; the business terms (BT-…) name the
EN 16931 semantics. Validated in CI with the KoSIT validator (`make einvoice`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from xml.etree.ElementTree import Element, SubElement, indent, register_namespace, tostring

from rhinvoice.infrastructure.einvoice.model import DISCOUNT_REASON_CODE, build

if TYPE_CHECKING:
    from datetime import date
    from decimal import Decimal

    from rhinvoice.application.document.einvoice import EInvoiceProfile
    from rhinvoice.application.document.printing import PrintModel
    from rhinvoice.domain.shared.address import Address
    from rhinvoice.infrastructure.einvoice.model import EInvoice, Line, Party, VatBreakdown

RSM = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
RAM = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
UDT = "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"
QDT = "urn:un:unece:uncefact:data:standard:QualifiedDataType:100"
for _prefix, _uri in (("rsm", RSM), ("ram", RAM), ("udt", UDT), ("qdt", QDT)):
    register_namespace(_prefix, _uri)

DATE_FORMAT = "102"
"""UNTDID 2379: CCYYMMDD."""
VAT = "VAT"
EMAIL_SCHEME = "EM"
VAT_SCHEME = "VA"
TAX_NUMBER_SCHEME = "FC"


def _ram(parent: Element, name: str, text: str | None = None, **attributes: str) -> Element:
    element = SubElement(parent, f"{{{RAM}}}{name}", attributes)
    if text is not None:
        element.text = text
    return element


def _unsigned_zero(value: Decimal) -> Decimal:
    """Zero without sign: a credit note's zero tax (0 x -1) is no "-0.00" (BR-CO-14)."""
    return value.copy_abs() if value.is_zero() else value


def _amount(value: Decimal) -> str:
    return f"{_unsigned_zero(value):.2f}"


def _number(value: Decimal) -> str:
    """Quantities, prices and rates without exponent or trailing zeros."""
    return format(_unsigned_zero(value).normalize(), "f")


def _date(parent: Element, name: str, value: date, namespace: str = UDT) -> None:
    holder = _ram(parent, name)
    element = SubElement(holder, f"{{{namespace}}}DateTimeString", {"format": DATE_FORMAT})
    element.text = value.strftime("%Y%m%d")


def _tax(parent: Element, category: str, rate: Decimal | None) -> None:
    _ram(parent, "TypeCode", VAT)
    _ram(parent, "CategoryCode", category)
    if rate is not None:
        _ram(parent, "RateApplicablePercent", _number(rate))


def _contact(parent: Element, party: Party) -> None:
    if party.contact is None:
        return
    contact = _ram(parent, "DefinedTradeContact")
    _ram(contact, "PersonName", party.contact)
    if party.phone is not None:
        _ram(_ram(contact, "TelephoneUniversalCommunication"), "CompleteNumber", party.phone)
    if party.email is not None:
        _ram(_ram(contact, "EmailURIUniversalCommunication"), "URIID", party.email)


def _address(parent: Element, address: Address) -> None:
    element = _ram(parent, "PostalTradeAddress")
    _ram(element, "PostcodeCode", address.postal_code)
    street = " ".join(part for part in (address.street, address.house_number) if part)
    lines = [line for line in (street, address.supplement) if line]
    for name, line in zip(("LineOne", "LineTwo"), lines, strict=False):
        _ram(element, name, line)
    _ram(element, "CityName", address.city)
    _ram(element, "CountryID", address.country.value)


def _party(parent: Element, name: str, party: Party) -> None:
    element = _ram(parent, name)
    _ram(element, "Name", party.name)
    if party.legal_info is not None:
        _ram(element, "Description", party.legal_info)
    if party.legal_id is not None:
        organization = _ram(element, "SpecifiedLegalOrganization")
        if party.legal_scheme is None:
            _ram(organization, "ID", party.legal_id)
        else:
            _ram(organization, "ID", party.legal_id, schemeID=party.legal_scheme)
    _contact(element, party)
    _address(element, party.address)
    if party.email is not None:
        _ram(
            _ram(element, "URIUniversalCommunication"), "URIID", party.email, schemeID=EMAIL_SCHEME
        )
    if party.vat_id is not None:
        _ram(_ram(element, "SpecifiedTaxRegistration"), "ID", party.vat_id, schemeID=VAT_SCHEME)
    if party.tax_number is not None:
        registration = _ram(element, "SpecifiedTaxRegistration")
        _ram(registration, "ID", party.tax_number, schemeID=TAX_NUMBER_SCHEME)


def _adjustment(parent: Element, amount: Decimal, *, charge: bool) -> None:
    """Write a line allowance or charge; the caller adds its reason."""
    element = _ram(parent, "SpecifiedTradeAllowanceCharge")
    indicator = _ram(element, "ChargeIndicator")
    SubElement(indicator, f"{{{UDT}}}Indicator").text = "true" if charge else "false"
    _ram(element, "ActualAmount", _amount(amount))


def _line(parent: Element, line: Line) -> None:
    item = _ram(parent, "IncludedSupplyChainTradeLineItem")
    _ram(_ram(item, "AssociatedDocumentLineDocument"), "LineID", str(line.position))
    product = _ram(item, "SpecifiedTradeProduct")
    _ram(product, "Name", line.name)
    if line.description:
        _ram(product, "Description", line.description)
    agreement = _ram(item, "SpecifiedLineTradeAgreement")
    _ram(_ram(agreement, "NetPriceProductTradePrice"), "ChargeAmount", _number(line.net_price))
    delivery = _ram(item, "SpecifiedLineTradeDelivery")
    _ram(delivery, "BilledQuantity", _number(line.quantity), unitCode=line.unit)
    settlement = _ram(item, "SpecifiedLineTradeSettlement")
    _tax(_ram(settlement, "ApplicableTradeTax"), line.category, line.rate)
    if line.allowance is not None:
        _adjustment(settlement, line.allowance, charge=False)
        if line.discount:
            _ram(settlement[-1], "ReasonCode", DISCOUNT_REASON_CODE)
        else:
            _ram(settlement[-1], "Reason", line.rounding)
    if line.charge is not None:
        _adjustment(settlement, line.charge, charge=True)
        _ram(settlement[-1], "Reason", line.rounding)
    summation = _ram(settlement, "SpecifiedTradeSettlementLineMonetarySummation")
    _ram(summation, "LineTotalAmount", _amount(line.net_amount))


def _breakdown(parent: Element, entry: VatBreakdown) -> None:
    tax = _ram(parent, "ApplicableTradeTax")
    _ram(tax, "CalculatedAmount", _amount(entry.tax))
    _ram(tax, "TypeCode", VAT)
    if entry.exemption_reason is not None:
        _ram(tax, "ExemptionReason", entry.exemption_reason)
    _ram(tax, "BasisAmount", _amount(entry.basis))
    _ram(tax, "CategoryCode", entry.category)
    if entry.exemption_code is not None:
        _ram(tax, "ExemptionReasonCode", entry.exemption_code)
    if entry.rate is not None:
        _ram(tax, "RateApplicablePercent", _number(entry.rate))


def _payment(settlement: Element, invoice: EInvoice) -> None:
    payment = invoice.payment
    if payment is None:
        return
    means = _ram(settlement, "SpecifiedTradeSettlementPaymentMeans")
    _ram(means, "TypeCode", payment.means)
    account = _ram(means, "PayeePartyCreditorFinancialAccount")
    _ram(account, "IBANID", payment.iban)
    _ram(account, "AccountName", payment.holder)
    if payment.bic is not None:
        _ram(_ram(means, "PayeeSpecifiedCreditorFinancialInstitution"), "BICID", payment.bic)


def _allowances(settlement: Element, invoice: EInvoice) -> None:
    for allowance in invoice.allowances:
        element = _ram(settlement, "SpecifiedTradeAllowanceCharge")
        indicator = _ram(element, "ChargeIndicator")
        SubElement(indicator, f"{{{UDT}}}Indicator").text = "false"
        _ram(element, "ActualAmount", _amount(allowance.amount))
        _ram(element, "ReasonCode", DISCOUNT_REASON_CODE)
        _ram(element, "Reason", allowance.reason)
        _tax(_ram(element, "CategoryTradeTax"), allowance.category, allowance.rate)


def _terms(settlement: Element, invoice: EInvoice) -> None:
    """BT-9 or BT-20: invoices have a due date, credit notes name the cancelled invoice."""
    terms = _ram(settlement, "SpecifiedTradePaymentTerms")
    if invoice.payment_terms is not None:
        _ram(terms, "Description", invoice.payment_terms)
    if invoice.due_date is not None:
        _date(terms, "DueDateDateTime", invoice.due_date)


def _summation(settlement: Element, invoice: EInvoice) -> None:
    summation = _ram(settlement, "SpecifiedTradeSettlementHeaderMonetarySummation")
    _ram(summation, "LineTotalAmount", _amount(invoice.line_total))
    if invoice.allowances:
        _ram(summation, "AllowanceTotalAmount", _amount(invoice.allowance_total))
    _ram(summation, "TaxBasisTotalAmount", _amount(invoice.tax_basis))
    currency = invoice.currency.value
    _ram(summation, "TaxTotalAmount", _amount(invoice.tax_total), currencyID=currency)
    if invoice.rounding:
        _ram(summation, "RoundingAmount", _amount(invoice.rounding))
    _ram(summation, "GrandTotalAmount", _amount(invoice.grand_total))
    _ram(summation, "DuePayableAmount", _amount(invoice.due_payable))


def _settlement(parent: Element, invoice: EInvoice) -> None:
    settlement = _ram(parent, "ApplicableHeaderTradeSettlement")
    if invoice.payment is not None:
        _ram(settlement, "PaymentReference", invoice.payment.remittance)
    _ram(settlement, "InvoiceCurrencyCode", invoice.currency.value)
    if invoice.payment is not None and invoice.payment.payee is not None:
        # BG-10: before the payment means, as the D16B schema orders the settlement.
        _ram(_ram(settlement, "PayeeTradeParty"), "Name", invoice.payment.payee)
    _payment(settlement, invoice)
    for entry in invoice.breakdown:
        _breakdown(settlement, entry)
    if invoice.period is not None:
        period = _ram(settlement, "BillingSpecifiedPeriod")
        _date(period, "StartDateTime", invoice.period[0])
        _date(period, "EndDateTime", invoice.period[1])
    _allowances(settlement, invoice)
    _terms(settlement, invoice)
    _summation(settlement, invoice)
    if invoice.preceding is not None:
        number, issued = invoice.preceding
        reference = _ram(settlement, "InvoiceReferencedDocument")
        _ram(reference, "IssuerAssignedID", number)
        _date(reference, "FormattedIssueDateTime", issued, QDT)


def cii(invoice: EInvoice) -> bytes:
    """Write the e-invoice as CII XML (UTF-8, with declaration)."""
    root = Element(f"{{{RSM}}}CrossIndustryInvoice")
    context = SubElement(root, f"{{{RSM}}}ExchangedDocumentContext")
    if invoice.business_process is not None:
        process = _ram(context, "BusinessProcessSpecifiedDocumentContextParameter")
        _ram(process, "ID", invoice.business_process)
    _ram(_ram(context, "GuidelineSpecifiedDocumentContextParameter"), "ID", invoice.specification)

    document = SubElement(root, f"{{{RSM}}}ExchangedDocument")
    _ram(document, "ID", invoice.number)
    _ram(document, "TypeCode", invoice.type_code)
    _date(document, "IssueDateTime", invoice.issue_date)
    for note in invoice.notes:
        _ram(_ram(document, "IncludedNote"), "Content", note)

    transaction = SubElement(root, f"{{{RSM}}}SupplyChainTradeTransaction")
    for line in invoice.lines:
        _line(transaction, line)
    agreement = _ram(transaction, "ApplicableHeaderTradeAgreement")
    if invoice.buyer_reference is not None:
        _ram(agreement, "BuyerReference", invoice.buyer_reference)
    _party(agreement, "SellerTradeParty", invoice.seller)
    _party(agreement, "BuyerTradeParty", invoice.buyer)
    if invoice.order_reference is not None:
        # BT-13 (EN 16931-3-3): after the parties, as the CII schema orders the agreement.
        order = _ram(agreement, "BuyerOrderReferencedDocument")
        _ram(order, "IssuerAssignedID", invoice.order_reference)
    delivery = _ram(transaction, "ApplicableHeaderTradeDelivery")
    if invoice.deliver_to is not None:
        name, address = invoice.deliver_to
        ship_to = _ram(delivery, "ShipToTradeParty")
        _ram(ship_to, "Name", name)
        _address(ship_to, address)
    event = _ram(delivery, "ActualDeliverySupplyChainEvent")
    _date(event, "OccurrenceDateTime", invoice.delivery_date)
    _settlement(transaction, invoice)

    indent(root)
    xml: bytes = tostring(root, encoding="utf-8", xml_declaration=True)
    return xml


class CiiWriter:
    """The e-invoice writer of the application (see EInvoiceWriter)."""

    def xml(self, model: PrintModel, profile: EInvoiceProfile) -> bytes:
        return cii(build(model, profile))
