# ruff: noqa: RUF001 - French and Italian elide with the typographic apostrophe.
"""E-invoices (EN 16931, CII): the business terms of each tax case.

The KoSIT validator judges the same samples against the official rules in
`make einvoice`; these tests pin what the e-invoice says and that its sums
add up like the printed invoice.
"""

import re
from dataclasses import replace
from decimal import Decimal
from xml.etree.ElementTree import Element, fromstring

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from rhinvoice.application.document.einvoice import (
    EInvoiceProblem,
    EInvoiceProfile,
    problems,
    seller_ids,
    vat_id,
)
from rhinvoice.application.document.handlers import DraftInput, LineInput
from rhinvoice.application.document.printing import PrintModel
from rhinvoice.domain.document.lines import LineKind, PriceMode
from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from rhinvoice.domain.shared.money import Currency, Money, round_half_up
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.treatment import TaxTreatment
from rhinvoice.domain.tax.vat_number import VatNumber
from rhinvoice.infrastructure.einvoice.cii import CiiWriter
from tests.einvoice_samples import model, samples
from tests.helpers import raises_exactly
from tests.unit.domain import factories

NAMESPACES = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
    "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
}
WRITER = CiiWriter()
SETTLEMENT = "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeSettlement"
SUMMATION = f"{SETTLEMENT}/ram:SpecifiedTradeSettlementHeaderMonetarySummation"
SELLER = "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeAgreement/ram:SellerTradeParty"
BUYER = "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeAgreement/ram:BuyerTradeParty"
LINES = "rsm:SupplyChainTradeTransaction/ram:IncludedSupplyChainTradeLineItem"


def xml(name: str, profile: EInvoiceProfile = EInvoiceProfile.EN16931) -> Element:
    printed = model(samples()[name])
    assert problems(printed, profile) == ()
    content = WRITER.xml(printed, profile)
    assert content.startswith(b"<?xml version='1.0' encoding='utf-8'?>")
    return fromstring(content)  # noqa: S314 - our own output


def text(root: Element, path: str) -> str:
    found = root.find(path, NAMESPACES)
    assert found is not None, path
    return found.text or ""


def texts(root: Element, path: str) -> list[str]:
    return [element.text or "" for element in root.findall(path, NAMESPACES)]


def amount(root: Element, path: str) -> Decimal:
    return Decimal(text(root, path))


def amounts(root: Element, path: str) -> list[Decimal]:
    return [Decimal(value) for value in texts(root, path)]


def absent(root: Element, path: str) -> bool:
    return root.find(path, NAMESPACES) is None


def check_sums(root: Element) -> None:
    """Check the sums of EN 16931 (BR-CO-10 to BR-CO-16), here exactly."""
    line_total = amount(root, f"{SUMMATION}/ram:LineTotalAmount")
    nets = amounts(
        root,
        f"{LINES}/ram:SpecifiedLineTradeSettlement/"
        "ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount",
    )
    assert sum(nets) == line_total
    allowances = sum(
        amounts(root, f"{SETTLEMENT}/ram:SpecifiedTradeAllowanceCharge/ram:ActualAmount"),
        Decimal(0),
    )
    allowance_total = (
        Decimal(0)
        if absent(root, f"{SUMMATION}/ram:AllowanceTotalAmount")
        else amount(root, f"{SUMMATION}/ram:AllowanceTotalAmount")
    )
    assert allowances == allowance_total
    basis = amount(root, f"{SUMMATION}/ram:TaxBasisTotalAmount")
    assert line_total - allowance_total == basis
    assert sum(amounts(root, f"{SETTLEMENT}/ram:ApplicableTradeTax/ram:BasisAmount")) == basis
    tax = amount(root, f"{SUMMATION}/ram:TaxTotalAmount")
    assert sum(amounts(root, f"{SETTLEMENT}/ram:ApplicableTradeTax/ram:CalculatedAmount")) == tax
    grand = amount(root, f"{SUMMATION}/ram:GrandTotalAmount")
    assert basis + tax == grand
    rounding = (
        Decimal(0)
        if absent(root, f"{SUMMATION}/ram:RoundingAmount")
        else amount(root, f"{SUMMATION}/ram:RoundingAmount")
    )
    assert grand + rounding == amount(root, f"{SUMMATION}/ram:DuePayableAmount")


@pytest.mark.parametrize("name", list(samples()))
def test_every_sample_adds_up(name: str) -> None:
    root = xml(name)
    check_sums(root)
    # Validators compare numbers as written: no zero carries a sign.
    signed_zero = re.compile(r"-0(\.0+)?")
    assert not [e.text for e in root.iter() if signed_zero.fullmatch((e.text or "").strip())]


def test_a_swiss_invoice() -> None:
    root = xml("ch-domestic")
    guideline = "rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID"
    assert text(root, guideline) == "urn:cen.eu:en16931:2017"
    assert absent(
        root, "rsm:ExchangedDocumentContext/ram:BusinessProcessSpecifiedDocumentContextParameter"
    )
    assert text(root, "rsm:ExchangedDocument/ram:ID") == "R20260001"
    assert text(root, "rsm:ExchangedDocument/ram:TypeCode") == "380"
    assert text(root, "rsm:ExchangedDocument/ram:IssueDateTime/udt:DateTimeString") == "20260302"
    assert texts(root, "rsm:ExchangedDocument/ram:IncludedNote/ram:Content") == ["Projekt Beispiel"]
    # The positions as printed: the heading is no position.
    assert texts(root, f"{LINES}/ram:AssociatedDocumentLineDocument/ram:LineID") == ["1", "2", "3"]
    assert texts(root, f"{LINES}/ram:SpecifiedTradeProduct/ram:Name") == [
        "Beratung",
        "Lizenz",
        "Fachbuch",
    ]
    assert texts(root, f"{LINES}/ram:SpecifiedTradeProduct/ram:Description") == ["Workshop vor Ort"]
    quantities = root.findall(
        f"{LINES}/ram:SpecifiedLineTradeDelivery/ram:BilledQuantity", NAMESPACES
    )
    assert [(item.text, item.get("unitCode")) for item in quantities] == [
        ("12.5", "HUR"),
        ("3", "C62"),
        ("2", "C62"),
    ]
    prices = (
        f"{LINES}/ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:ChargeAmount"
    )
    assert texts(root, prices) == ["150", "99.9", "38.5"]
    line_settlement = f"{LINES}/ram:SpecifiedLineTradeSettlement"
    assert texts(root, f"{line_settlement}/ram:ApplicableTradeTax/ram:RateApplicablePercent") == [
        "8.1",
        "8.1",
        "2.6",
    ]
    # 3 x 99.90 less 10 %.
    discount = f"{line_settlement}/ram:SpecifiedTradeAllowanceCharge"
    assert texts(root, f"{discount}/ram:ActualAmount") == ["29.97"]
    assert texts(root, f"{discount}/ram:ReasonCode") == ["95"]
    assert texts(root, f"{discount}/ram:ChargeIndicator/udt:Indicator") == ["false"]


def test_the_parties_of_a_swiss_invoice() -> None:
    root = xml("ch-domestic")
    agreement = "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeAgreement"
    assert text(root, f"{agreement}/ram:BuyerReference") == "PO-4711"
    assert text(root, f"{SELLER}/ram:Name") == "Muster Werkstatt GmbH"
    assert text(root, f"{SELLER}/ram:Description") == "Handelsregister des Kantons Zürich"
    legal = root.find(f"{SELLER}/ram:SpecifiedLegalOrganization/ram:ID", NAMESPACES)
    assert legal is not None
    assert (legal.text, legal.get("schemeID")) == ("CHE123456788", "0183")
    contact = f"{SELLER}/ram:DefinedTradeContact"
    assert text(root, f"{contact}/ram:PersonName") == "Muster Werkstatt GmbH"
    assert text(root, f"{contact}/ram:TelephoneUniversalCommunication/ram:CompleteNumber") == (
        "+41 71 123 45 67"
    )
    assert text(root, f"{contact}/ram:EmailURIUniversalCommunication/ram:URIID") == (
        "info@muster-werkstatt.example"
    )
    address = f"{SELLER}/ram:PostalTradeAddress"
    assert [
        text(root, f"{address}/ram:{part}")
        for part in ("PostcodeCode", "LineOne", "CityName", "CountryID")
    ] == ["8001", "Bahnhofstrasse 1", "Zürich", "CH"]
    endpoint = root.find(f"{SELLER}/ram:URIUniversalCommunication/ram:URIID", NAMESPACES)
    assert endpoint is not None
    assert (endpoint.text, endpoint.get("schemeID")) == ("info@muster-werkstatt.example", "EM")
    registration = root.findall(f"{SELLER}/ram:SpecifiedTaxRegistration/ram:ID", NAMESPACES)
    assert [(item.text, item.get("schemeID")) for item in registration] == [
        ("CHE123456788MWST", "VA")
    ]
    assert text(root, f"{BUYER}/ram:Name") == "Beispiel AG"
    assert absent(root, f"{BUYER}/ram:SpecifiedTaxRegistration")
    assert absent(root, f"{BUYER}/ram:URIUniversalCommunication")
    assert absent(root, f"{BUYER}/ram:DefinedTradeContact")


def test_the_settlement_of_a_swiss_invoice() -> None:
    root = xml("ch-domestic")
    # The service period, delivered at its end.
    delivery = "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeDelivery"
    event = f"{delivery}/ram:ActualDeliverySupplyChainEvent/ram:OccurrenceDateTime"
    assert text(root, f"{event}/udt:DateTimeString") == "20260228"
    period = f"{SETTLEMENT}/ram:BillingSpecifiedPeriod"
    assert text(root, f"{period}/ram:StartDateTime/udt:DateTimeString") == "20260201"
    assert text(root, f"{period}/ram:EndDateTime/udt:DateTimeString") == "20260228"

    # Paid to the QR-IBAN with the QR reference of the payment part.
    assert text(root, f"{SETTLEMENT}/ram:PaymentReference") == "000000000000002026202600017"
    assert text(root, f"{SETTLEMENT}/ram:InvoiceCurrencyCode") == "CHF"
    means = f"{SETTLEMENT}/ram:SpecifiedTradeSettlementPaymentMeans"
    assert text(root, f"{means}/ram:TypeCode") == "30"
    assert text(root, f"{means}/ram:PayeePartyCreditorFinancialAccount/ram:IBANID") == (
        factories.CH_QR_IBAN
    )
    assert text(root, f"{means}/ram:PayeePartyCreditorFinancialAccount/ram:AccountName") == (
        "Muster GmbH"
    )
    assert absent(root, f"{means}/ram:PayeeSpecifiedCreditorFinancialInstitution")
    terms = f"{SETTLEMENT}/ram:SpecifiedTradePaymentTerms"
    assert text(root, f"{terms}/ram:DueDateDateTime/udt:DateTimeString") == "20260401"
    assert absent(root, f"{terms}/ram:Description")

    # Per rate: the document discount of 2.5 % and the tax.
    taxes = f"{SETTLEMENT}/ram:ApplicableTradeTax"
    assert texts(root, f"{taxes}/ram:CategoryCode") == ["S", "S"]
    assert texts(root, f"{taxes}/ram:RateApplicablePercent") == ["8.1", "2.6"]
    assert texts(root, f"{taxes}/ram:BasisAmount") == ["2091.11", "75.07"]
    assert texts(root, f"{taxes}/ram:CalculatedAmount") == ["169.38", "1.95"]
    assert absent(root, f"{taxes}/ram:ExemptionReason")
    allowance = f"{SETTLEMENT}/ram:SpecifiedTradeAllowanceCharge"
    assert texts(root, f"{allowance}/ram:ActualAmount") == ["53.62", "1.93"]
    assert texts(root, f"{allowance}/ram:Reason") == ["Rabatt", "Rabatt"]
    assert texts(root, f"{allowance}/ram:CategoryTradeTax/ram:RateApplicablePercent") == [
        "8.1",
        "2.6",
    ]
    # The Swiss 5-centime rounding.
    assert amount(root, f"{SUMMATION}/ram:RoundingAmount") == Decimal("-0.01")
    assert amount(root, f"{SUMMATION}/ram:DuePayableAmount") == Decimal("2337.50")
    currency = root.find(f"{SUMMATION}/ram:TaxTotalAmount", NAMESPACES)
    assert currency is not None
    assert currency.get("currencyID") == "CHF"


def test_a_cancellation_is_a_credit_note() -> None:
    root = xml("ch-domestic-cancellation")
    assert text(root, "rsm:ExchangedDocument/ram:TypeCode") == "381"
    assert text(root, "rsm:ExchangedDocument/ram:ID") == "S20260001"
    quantities = texts(root, f"{LINES}/ram:SpecifiedLineTradeDelivery/ram:BilledQuantity")
    assert quantities == ["12.5", "3"]
    reference = f"{SETTLEMENT}/ram:InvoiceReferencedDocument"
    assert text(root, f"{reference}/ram:IssuerAssignedID") == "R20260001"
    assert text(root, f"{reference}/ram:FormattedIssueDateTime/qdt:DateTimeString") == "20260302"
    # No payment asked for: the terms name the cancelled invoice.
    assert absent(root, f"{SETTLEMENT}/ram:SpecifiedTradeSettlementPaymentMeans")
    assert absent(root, f"{SETTLEMENT}/ram:PaymentReference")
    terms = f"{SETTLEMENT}/ram:SpecifiedTradePaymentTerms"
    assert text(root, f"{terms}/ram:Description") == "Storniert die Rechnung R20260001"
    assert absent(root, f"{terms}/ram:DueDateDateTime")
    assert amount(root, f"{SUMMATION}/ram:DuePayableAmount") > 0


def test_an_export_from_switzerland() -> None:
    root = xml("ch-export")
    assert text(root, f"{SETTLEMENT}/ram:InvoiceCurrencyCode") == "EUR"
    taxes = f"{SETTLEMENT}/ram:ApplicableTradeTax"
    assert texts(root, f"{taxes}/ram:CategoryCode") == ["G"]
    assert texts(root, f"{taxes}/ram:RateApplicablePercent") == ["0"]
    assert texts(root, f"{taxes}/ram:ExemptionReasonCode") == ["VATEX-EU-G"]
    assert text(root, f"{taxes}/ram:ExemptionReason") == (
        "Ort der Leistung im Ausland, nicht der MWST unterstellt."
    )
    means = f"{SETTLEMENT}/ram:SpecifiedTradeSettlementPaymentMeans"
    assert text(root, f"{means}/ram:TypeCode") == "58"
    assert text(root, f"{means}/ram:PayeeSpecifiedCreditorFinancialInstitution/ram:BICID") == (
        "COBADEFFXXX"
    )
    # No QR-bill abroad: the invoice number is the reference.
    assert text(root, f"{SETTLEMENT}/ram:PaymentReference") == "R20260001"
    assert absent(root, f"{BUYER}/ram:SpecifiedTaxRegistration")


def test_reverse_charge_from_switzerland() -> None:
    root = xml("ch-reverse-charge")
    taxes = f"{SETTLEMENT}/ram:ApplicableTradeTax"
    assert texts(root, f"{taxes}/ram:CategoryCode") == ["AE"]
    assert texts(root, f"{BUYER}/ram:SpecifiedTaxRegistration/ram:ID") == ["DE987654321"]


def test_a_swiss_small_business_is_outside_vat() -> None:
    root = xml("ch-small-business")
    taxes = f"{SETTLEMENT}/ram:ApplicableTradeTax"
    assert texts(root, f"{taxes}/ram:CategoryCode") == ["O"]
    assert absent(root, f"{taxes}/ram:RateApplicablePercent")
    assert texts(root, f"{taxes}/ram:ExemptionReasonCode") == ["VATEX-EU-O"]
    line_tax = f"{LINES}/ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax"
    assert texts(root, f"{line_tax}/ram:CategoryCode") == ["O"]
    assert absent(root, f"{line_tax}/ram:RateApplicablePercent")
    # The UID identifies the business; it is no VAT number.
    assert absent(root, f"{SELLER}/ram:SpecifiedTaxRegistration")
    assert text(root, f"{SELLER}/ram:SpecifiedLegalOrganization/ram:ID") == "CHE123456788"
    assert absent(root, f"{SELLER}/ram:Description")
    assert absent(root, f"{SELLER}/ram:DefinedTradeContact")


def test_gross_prices_become_net_amounts() -> None:
    root = xml("de-domestic-gross")
    taxes = f"{SETTLEMENT}/ram:ApplicableTradeTax"
    assert texts(root, f"{taxes}/ram:RateApplicablePercent") == ["19", "7"]
    prices = (
        f"{LINES}/ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:ChargeAmount"
    )
    # 150 / 1.19, 99.90 / 1.19, 38.50 / 1.07, 100 / 1.19 to four places.
    assert texts(root, prices) == ["126.0504", "83.9496", "35.9813", "84.0336"]
    quantities = texts(root, f"{LINES}/ram:SpecifiedLineTradeDelivery/ram:BilledQuantity")
    assert quantities == ["12.5", "3", "2", "-1"]
    nets = amounts(
        root,
        f"{LINES}/ram:SpecifiedLineTradeSettlement/"
        "ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount",
    )
    assert nets == [Decimal("1575.63"), Decimal("226.66"), Decimal("71.96"), Decimal("-84.03")]
    allowance = f"{LINES}/ram:SpecifiedLineTradeSettlement/ram:SpecifiedTradeAllowanceCharge"
    # 3 x 83.9496 = 251.85, less the net of the discounted line.
    assert amounts(root, f"{allowance}/ram:ActualAmount") == [Decimal("25.19")]
    delivery = "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeDelivery"
    event = f"{delivery}/ram:ActualDeliverySupplyChainEvent/ram:OccurrenceDateTime"
    assert text(root, f"{event}/udt:DateTimeString") == "20260227"
    assert texts(root, f"{BUYER}/ram:Name") == ["Erika Mustermann"]
    assert text(root, f"{BUYER}/ram:URIUniversalCommunication/ram:URIID") == "erika@example.com"
    printed = model(samples()["de-domestic-gross"])
    assert amount(root, f"{SUMMATION}/ram:DuePayableAmount") == printed.view.totals.total.amount


def test_reverse_charge() -> None:
    root = xml("de-reverse-charge")
    taxes = f"{SETTLEMENT}/ram:ApplicableTradeTax"
    assert texts(root, f"{taxes}/ram:CategoryCode") == ["AE"]
    assert texts(root, f"{taxes}/ram:RateApplicablePercent") == ["0"]
    assert texts(root, f"{taxes}/ram:CalculatedAmount") == ["0.00"]
    assert texts(root, f"{taxes}/ram:ExemptionReasonCode") == ["VATEX-EU-AE"]
    registration = root.findall(f"{SELLER}/ram:SpecifiedTaxRegistration/ram:ID", NAMESPACES)
    assert [(item.text, item.get("schemeID")) for item in registration] == [
        ("DE123456789", "VA"),
        ("27/123/45678", "FC"),
    ]
    legal = root.find(f"{SELLER}/ram:SpecifiedLegalOrganization/ram:ID", NAMESPACES)
    assert legal is not None
    assert (legal.text, legal.get("schemeID")) == (
        "HRB 123456, Amtsgericht Berlin-Charlottenburg",
        None,
    )
    assert texts(root, f"{BUYER}/ram:SpecifiedTaxRegistration/ram:ID") == ["ATU12345675"]


DELIVERY = "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeDelivery"


def test_an_intra_community_supply() -> None:
    root = xml("de-intra-community")
    taxes = f"{SETTLEMENT}/ram:ApplicableTradeTax"
    assert texts(root, f"{taxes}/ram:CategoryCode") == ["AE", "K"]
    assert texts(root, f"{taxes}/ram:ExemptionReasonCode") == ["VATEX-EU-AE", "VATEX-EU-IC"]
    assert texts(root, f"{taxes}/ram:ExemptionReason") == [
        "Steuerschuldnerschaft des Leistungsempfängers.",
        "Steuerfreie innergemeinschaftliche Lieferung (§ 4 Nr. 1 Buchst. b i. V. m. § 6a UStG).",
    ]
    line_tax = f"{LINES}/ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax"
    assert texts(root, f"{line_tax}/ram:CategoryCode") == ["AE", "K", "K"]
    # The goods go to the delivery address in Linz (BR-IC-12), the invoice to Vienna.
    ship_to = f"{DELIVERY}/ram:ShipToTradeParty"
    assert text(root, f"{ship_to}/ram:Name") == "Kunde Österreich GmbH"
    assert text(root, f"{ship_to}/ram:PostalTradeAddress/ram:CityName") == "Linz"
    assert text(root, f"{ship_to}/ram:PostalTradeAddress/ram:CountryID") == "AT"
    assert texts(root, f"{BUYER}/ram:SpecifiedTaxRegistration/ram:ID") == ["ATU12345675"]


def test_a_cancelled_intra_community_supply_ships_to_the_customer() -> None:
    root = xml("de-intra-community-cancellation")
    assert text(root, "rsm:ExchangedDocument/ram:TypeCode") == "381"
    # No VAT on a credit note is 0.00, not -0.00 (Mustang: BR-CO-14).
    assert text(root, f"{SUMMATION}/ram:TaxTotalAmount") == "0.00"
    taxes = f"{SETTLEMENT}/ram:ApplicableTradeTax"
    assert texts(root, f"{taxes}/ram:CategoryCode") == ["K"]
    address = f"{DELIVERY}/ram:ShipToTradeParty/ram:PostalTradeAddress"
    assert text(root, f"{address}/ram:CityName") == "Wien"


def test_goods_leaving_the_vat_area_are_exports() -> None:
    austrian = xml("at-goods-export")
    taxes = f"{SETTLEMENT}/ram:ApplicableTradeTax"
    assert texts(austrian, f"{taxes}/ram:CategoryCode") == ["S", "G"]
    assert texts(austrian, f"{taxes}/ram:RateApplicablePercent") == ["20", "0"]
    assert texts(austrian, f"{taxes}/ram:ExemptionReason") == [
        "Steuerfreie Ausfuhrlieferung (§ 6 Abs. 1 Z 1 i. V. m. § 7 UStG).",
    ]
    assert absent(austrian, f"{DELIVERY}/ram:ShipToTradeParty")
    swiss = xml("ch-goods-export")
    assert texts(swiss, f"{taxes}/ram:CategoryCode") == ["AE", "G"]
    assert texts(swiss, f"{taxes}/ram:ExemptionReason")[1] == (
        "Steuerbefreite Ausfuhrlieferung (Art. 23 Abs. 2 Ziff. 1 MWSTG)."
    )


def test_french_and_italian_invoices_give_their_notices_as_exemption_reasons() -> None:
    taxes = f"{SETTLEMENT}/ram:ApplicableTradeTax"
    french = xml("ch-export-french")
    assert texts(french, f"{taxes}/ram:CategoryCode") == ["G"]
    assert texts(french, f"{taxes}/ram:ExemptionReason") == [
        (
            "Lieu de la prestation de services à l’étranger, non soumis à la TVA."
            " Livraison à l’exportation exonérée de l’impôt (art. 23, al. 2, ch. 1, LTVA)."
        ),
    ]
    italian = xml("de-intra-community-italian")
    assert texts(italian, f"{taxes}/ram:CategoryCode") == ["AE", "K"]
    assert texts(italian, f"{taxes}/ram:ExemptionReason") == [
        "Inversione contabile.",
        "Cessione intracomunitaria esente (§ 4 Nr. 1 Buchst. b i. V. m. § 6a UStG).",
    ]


def test_a_service_and_a_goods_export_share_the_category() -> None:
    printed = model(samples()["ch-goods-export"])
    content = printed.view.document.content
    # Services exported too: one G group naming both notices.
    services = replace(
        printed.view,
        notices=(
            (TaxTreatment.EXPORT, "Ort der Leistung im Ausland."),
            (TaxTreatment.GOODS_EXPORT, "Ausfuhrlieferung."),
        ),
    )
    assert content.goods_treatment is TaxTreatment.GOODS_EXPORT
    root = fromstring(WRITER.xml(replace(printed, view=services), EInvoiceProfile.EN16931))  # noqa: S314
    taxes = f"{SETTLEMENT}/ram:ApplicableTradeTax"
    assert texts(root, f"{taxes}/ram:ExemptionReason")[1] == (
        "Ort der Leistung im Ausland. Ausfuhrlieferung."
    )


def test_a_german_small_business_is_exempt() -> None:
    root = xml("de-small-business")
    taxes = f"{SETTLEMENT}/ram:ApplicableTradeTax"
    assert texts(root, f"{taxes}/ram:CategoryCode") == ["E"]
    assert "§ 19" in text(root, f"{taxes}/ram:ExemptionReason")
    assert absent(root, f"{taxes}/ram:ExemptionReasonCode")
    assert texts(root, f"{SELLER}/ram:SpecifiedTaxRegistration/ram:ID") == ["27/123/45678"]


def test_xrechnung_for_an_authority() -> None:
    root = xml("de-authority", EInvoiceProfile.XRECHNUNG)
    context = "rsm:ExchangedDocumentContext"
    assert text(root, f"{context}/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID") == (
        "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
    )
    assert text(root, f"{context}/ram:BusinessProcessSpecifiedDocumentContextParameter/ram:ID") == (
        "urn:fdc:peppol.eu:2017:poacc:billing:01.0"
    )
    agreement = "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeAgreement"
    assert text(root, f"{agreement}/ram:BuyerReference") == "04011000-12345-34"
    assert text(root, f"{BUYER}/ram:DefinedTradeContact/ram:PersonName") == "Frau Beispiel"


def test_austrian_rates() -> None:
    root = xml("at-domestic")
    taxes = f"{SETTLEMENT}/ram:ApplicableTradeTax"
    assert texts(root, f"{taxes}/ram:RateApplicablePercent") == ["20", "10"]


def test_exempt_lines_of_a_taxed_invoice_name_a_reason() -> None:
    sample = samples()["ch-domestic"]
    printed = model(sample)
    view = replace(printed.view, notices=((TaxTreatment.DOMESTIC, ""),))
    totals = view.totals
    group = replace(
        totals.groups[1],
        vat_code=type(totals.groups[1].vat_code)("E"),
        rate=Decimal(0),
        tax=type(totals.groups[1].tax)(Decimal(0), totals.currency),
    )
    lines = tuple(
        replace(line, vat_code=group.vat_code, tax_rate=Decimal(0))
        if line.tax_rate == Decimal("2.6")
        else line
        for line in totals.lines
    )
    exempt = replace(
        printed,
        view=replace(view, totals=replace(totals, groups=(totals.groups[0], group), lines=lines)),
    )
    root = fromstring(WRITER.xml(exempt, EInvoiceProfile.EN16931))  # noqa: S314 - our own
    taxes = f"{SETTLEMENT}/ram:ApplicableTradeTax"
    assert texts(root, f"{taxes}/ram:ExemptionReason") == ["Steuerbefreite Leistung"]


def found(
    printed: PrintModel, profile: EInvoiceProfile = EInvoiceProfile.EN16931
) -> set[EInvoiceProblem]:
    return set(problems(printed, profile))


def test_what_keeps_an_invoice_from_being_an_e_invoice() -> None:
    reverse = model(samples()["de-reverse-charge"])
    nameless = replace(
        reverse,
        company=replace(reverse.company, vat_number=None, commercial_register=" "),
        recipient=replace(reverse.recipient, vat_number=None) if reverse.recipient else None,
    )
    assert found(nameless) == {
        EInvoiceProblem.SELLER_ID_MISSING,
        EInvoiceProblem.SELLER_VAT_ID_MISSING,
        EInvoiceProblem.BUYER_VAT_ID_MISSING,
    }
    domestic = model(samples()["at-domestic"])
    untaxed = replace(domestic, company=replace(domestic.company, vat_number=None, tax_number=" "))
    assert found(untaxed) == {
        EInvoiceProblem.SELLER_ID_MISSING,
        EInvoiceProblem.SELLER_TAX_ID_MISSING,
    }
    # A tax number is enough for a domestic invoice, with a register entry to identify the seller.
    numbered = replace(
        domestic,
        company=replace(
            domestic.company, vat_number=None, tax_number="123/456", commercial_register="FN 1a"
        ),
    )
    assert found(numbered) == set()
    # Reverse charge needs a buyer VAT number with country prefix (BR-AE-02).
    assert reverse.recipient is not None
    prefixless = replace(reverse.recipient, vat_number=VatNumber("12345675"))
    assert found(replace(reverse, recipient=prefixless)) == {EInvoiceProblem.BUYER_VAT_ID_MISSING}
    # So does an intra-Community supply, and the seller's VAT ID (BR-IC-02).
    goods = model(samples()["de-intra-community-cancellation"])
    assert goods.recipient is not None
    assert found(
        replace(
            goods,
            company=replace(goods.company, vat_number=None),
            recipient=replace(goods.recipient, vat_number=VatNumber("12345675")),
        )
    ) == {EInvoiceProblem.SELLER_VAT_ID_MISSING, EInvoiceProblem.BUYER_VAT_ID_MISSING}


def test_what_xrechnung_asks_for_beyond_en_16931() -> None:
    printed = model(samples()["ch-domestic"])
    assert found(printed, EInvoiceProfile.XRECHNUNG) == {EInvoiceProblem.BUYER_EMAIL_MISSING}
    document = printed.view.document
    bare = replace(
        printed,
        view=replace(
            printed.view,
            document=replace(document, content=replace(document.content, reference=" ")),
        ),
        company=replace(printed.company, email=None, phone=" "),
        bank_account=None,
    )
    assert found(bare, EInvoiceProfile.XRECHNUNG) == {
        EInvoiceProblem.BUYER_REFERENCE_MISSING,
        EInvoiceProblem.SELLER_EMAIL_MISSING,
        EInvoiceProblem.SELLER_PHONE_MISSING,
        EInvoiceProblem.BUYER_EMAIL_MISSING,
        EInvoiceProblem.BANK_ACCOUNT_MISSING,
    }
    assert found(bare) == set()
    # Credit notes need payment instructions as well (BR-DE-1).
    cancellation = model(samples()["ch-domestic-cancellation"])
    assert EInvoiceProblem.BANK_ACCOUNT_MISSING in found(
        replace(cancellation, cancelled_account=None), EInvoiceProfile.XRECHNUNG
    )


def test_an_e_invoice_needs_a_customer() -> None:
    printed = replace(model(samples()["ch-domestic"]), recipient=None)
    with raises_exactly(InvalidStateError, "an e-invoice needs a customer"):
        problems(printed, EInvoiceProfile.EN16931)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CHE-123.456.788 MWST", "CHE123456788MWST"),
        ("DE 123 456 789", "DE123456789"),
        ("atu12345675", "ATU12345675"),
        ("12345", None),
    ],
)
def test_vat_ids(raw: str, expected: str | None) -> None:
    assert vat_id(raw) == expected


def test_the_identifiers_of_the_seller() -> None:
    swiss = seller_ids(factories.company(commercial_register="CH-020.3.012.345-6"))
    assert (
        swiss.vat_id,
        swiss.tax_number,
        swiss.legal_id,
        swiss.legal_scheme,
        swiss.legal_info,
    ) == (
        "CHE123456788MWST",
        None,
        "CHE123456788",
        "0183",
        "CH-020.3.012.345-6",
    )
    # A VAT number without country prefix is a tax registration (BT-32).
    liechtenstein = seller_ids(factories.company(vat_number=VatNumber("54321")))
    assert (liechtenstein.vat_id, liechtenstein.tax_number, liechtenstein.legal_id) == (
        None,
        "54321",
        None,
    )
    # Registered for VAT: the UID is the MWST number, also without the suffix.
    typed = seller_ids(factories.company(vat_number=VatNumber.parse("CHE-123.456.788")))
    assert (typed.vat_id, typed.legal_id) == ("CHE123456788", "CHE123456788")
    small = seller_ids(
        factories.company(vat_number=VatNumber.parse("CHE-123.456.788"), small_business=True)
    )
    assert (small.vat_id, small.legal_id) == (None, "CHE123456788")
    # Typed without space before MWST: the UID is still its first twelve characters.
    glued = seller_ids(factories.company(vat_number=VatNumber("CHE-123.456.788MWST")))
    assert (glued.vat_id, glued.legal_id) == ("CHE123456788MWST", "CHE123456788")
    nothing = seller_ids(factories.company(vat_number=None))
    assert (nothing.vat_id, nothing.tax_number, nothing.legal_id, nothing.legal_info) == (
        None,
        None,
        None,
        None,
    )


def test_a_buyer_with_a_contact_and_a_post_office_box() -> None:
    printed = model(samples()["de-authority"])
    assert printed.recipient is not None
    address = replace(
        printed.recipient.address, street="", house_number="", supplement="Postfach 12"
    )
    recipient = replace(printed.recipient, email=None, address=address)
    root = fromstring(WRITER.xml(replace(printed, recipient=recipient), EInvoiceProfile.EN16931))  # noqa: S314
    contact = f"{BUYER}/ram:DefinedTradeContact"
    assert text(root, f"{contact}/ram:PersonName") == "Frau Beispiel"
    assert absent(root, f"{contact}/ram:EmailURIUniversalCommunication")
    assert absent(root, f"{contact}/ram:TelephoneUniversalCommunication")
    assert texts(root, f"{BUYER}/ram:PostalTradeAddress/ram:LineOne") == ["Postfach 12"]
    assert absent(root, f"{BUYER}/ram:PostalTradeAddress/ram:LineTwo")
    seller = f"{SELLER}/ram:PostalTradeAddress"
    assert texts(root, f"{seller}/ram:LineOne") == ["Hauptstraße 7"]


QUANTITIES = st.decimals(min_value=Decimal(-20), max_value=Decimal(50), places=2).filter(bool)
PRICES = st.decimals(min_value=Decimal("0.05"), max_value=Decimal(5000), places=2)
DISCOUNTS = st.sampled_from([Decimal(0), Decimal(5), Decimal("12.5"), Decimal(50)])
CATEGORIES = st.sampled_from([TaxCategory.STANDARD, TaxCategory.REDUCED, TaxCategory.SPECIAL])


@st.composite
def drafts(draw: st.DrawFn) -> DraftInput:
    lines = tuple(
        LineInput(
            kind=LineKind.ITEM,
            description=f"Position {index}",
            quantity=str(draw(QUANTITIES)),
            unit_price=str(draw(PRICES)),
            discount_percent=str(draw(DISCOUNTS)),
            tax_category=draw(CATEGORIES),
        )
        for index in range(draw(st.integers(min_value=1, max_value=6)))
    )
    sample = samples()["ch-domestic"].draft
    return replace(
        sample,
        lines=lines,
        price_mode=draw(st.sampled_from(PriceMode)),
        discount_value=str(draw(DISCOUNTS)),
        reference="",
        service_from=None,
        service_to=None,
    )


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(drafts(), st.booleans())
def test_every_line_adds_up(draft: DraftInput, cancel: bool) -> None:
    """Quantity x net price less allowance plus charge is the line amount, to the cent."""
    sample = replace(samples()["ch-domestic"], draft=draft, cancel=cancel)
    try:
        printed = model(sample)
    except ValidationError:
        # Invoices with a total of zero or below are refused when issuing.
        return
    root = fromstring(WRITER.xml(printed, EInvoiceProfile.EN16931))  # noqa: S314 - our own
    for item in root.findall(LINES, NAMESPACES):
        quantity = amount(item, "ram:SpecifiedLineTradeDelivery/ram:BilledQuantity")
        price = amount(
            item, "ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:ChargeAmount"
        )
        assert price >= 0
        adjustments = Decimal(0)
        for adjustment in item.findall(
            "ram:SpecifiedLineTradeSettlement/ram:SpecifiedTradeAllowanceCharge", NAMESPACES
        ):
            value = amount(adjustment, "ram:ActualAmount")
            charge = text(adjustment, "ram:ChargeIndicator/udt:Indicator") == "true"
            adjustments += value if charge else -value
            assert not absent(adjustment, "ram:ReasonCode") or not absent(adjustment, "ram:Reason")
        net = amount(
            item,
            "ram:SpecifiedLineTradeSettlement/"
            "ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount",
        )
        assert round_half_up(quantity * price, Decimal("0.01")) + adjustments == net
    check_sums(root)
    assert amount(root, f"{SUMMATION}/ram:DuePayableAmount") == abs(
        printed.view.totals.total.amount
    )


def test_a_credit_note_as_xrechnung_names_the_account_of_the_invoice() -> None:
    root = xml("de-authority-cancellation", EInvoiceProfile.XRECHNUNG)
    assert text(root, "rsm:ExchangedDocument/ram:TypeCode") == "381"
    means = f"{SETTLEMENT}/ram:SpecifiedTradeSettlementPaymentMeans"
    assert text(root, f"{means}/ram:TypeCode") == "58"
    assert text(root, f"{means}/ram:PayeePartyCreditorFinancialAccount/ram:IBANID") == (
        "DE89370400440532013000"
    )
    # Embedded in the PDF, a credit note asks for no payment.
    assert absent(xml("de-authority-cancellation"), means)


def test_qr_ibans_take_no_sepa_payments() -> None:
    printed = model(samples()["ch-domestic"])
    assert printed.bank_account is not None
    euro = replace(
        printed,
        bank_account=replace(printed.bank_account, currency=Currency.EUR),
        view=replace(
            printed.view,
            totals=replace(
                printed.view.totals,
                currency=Currency.EUR,
                total=Money(printed.view.totals.total.amount, Currency.EUR),
            ),
        ),
    )
    root = fromstring(WRITER.xml(euro, EInvoiceProfile.EN16931))  # noqa: S314 - our own
    means = f"{SETTLEMENT}/ram:SpecifiedTradeSettlementPaymentMeans"
    assert text(root, f"{means}/ram:PayeePartyCreditorFinancialAccount/ram:IBANID") == (
        factories.CH_QR_IBAN
    )
    assert text(root, f"{means}/ram:TypeCode") == "30"


def test_discounted_credit_lines_keep_their_discount() -> None:
    root = xml("de-mixed")
    credit = root.findall(LINES, NAMESPACES)[-1]
    assert text(credit, "ram:SpecifiedLineTradeDelivery/ram:BilledQuantity") == "-2"
    discount = "ram:SpecifiedLineTradeSettlement/ram:SpecifiedTradeAllowanceCharge"
    # -2 x 33.33 = -66.66, less 15 %: -56.66; the discount is negative like the line.
    assert text(credit, f"{discount}/ram:ActualAmount") == "-10.00"
    assert text(credit, f"{discount}/ram:ReasonCode") == "95"
    taxes = f"{SETTLEMENT}/ram:ApplicableTradeTax"
    assert texts(root, f"{taxes}/ram:CategoryCode") == ["S", "Z", "E"]
    assert text(root, "rsm:ExchangedDocument/ram:IncludedNote/ram:Content") == (
        'Projekt "A & B" <2026>'
    )


def test_gross_rounding_is_a_line_charge_or_allowance() -> None:
    root = xml("ch-domestic-gross")
    reasons = texts(
        root,
        f"{LINES}/ram:SpecifiedLineTradeSettlement/ram:SpecifiedTradeAllowanceCharge/ram:Reason",
    )
    assert set(reasons) <= {"Rundung"}
    assert reasons


def test_gross_rounding_can_be_a_line_charge() -> None:
    def reduced(quantity: str, price: str) -> LineInput:
        return LineInput(
            kind=LineKind.ITEM,
            description="Buch",
            quantity=quantity,
            unit_price=price,
            tax_category=TaxCategory.REDUCED,
        )

    sample = samples()["ch-domestic"]
    draft = replace(
        sample.draft,
        lines=(reduced("6", "82.06"), reduced("9", "31.11"), reduced("5", "96.27")),
        price_mode=PriceMode.GROSS,
        discount_value=None,
    )
    root = fromstring(WRITER.xml(model(replace(sample, draft=draft)), EInvoiceProfile.EN16931))  # noqa: S314 - our own output
    charges = root.findall(
        f"{LINES}/ram:SpecifiedLineTradeSettlement/ram:SpecifiedTradeAllowanceCharge", NAMESPACES
    )
    assert [
        (text(item, "ram:ChargeIndicator/udt:Indicator"), text(item, "ram:ActualAmount"))
        for item in charges
    ] == [("true", "0.01")]
    assert texts(
        root,
        f"{LINES}/ram:SpecifiedLineTradeSettlement/ram:SpecifiedTradeAllowanceCharge/ram:Reason",
    ) == ["Rundung"]
    check_sums(root)
