"""What Rhinvoice knows about the country of a company: one profile per country.

A profile gathers the rules and words that differ between countries: VAT law and
rates, legal notices, what an invoice must state, payment codes, number format and
the terms printed on documents. Everything else in Rhinvoice asks the profile
instead of naming countries. Adding a country means writing one profile module and
registering it (see docs/adding-a-country.md and ADR 0017).

Not tax advice.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.tax.rates import rate_set_on
from rhinvoice.domain.tax.treatment import TaxTreatment

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from datetime import date

    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.customer.customer import Customer
    from rhinvoice.domain.shared.country import Country
    from rhinvoice.domain.shared.money import Currency, Money
    from rhinvoice.domain.tax.rates import TaxRateSet
    from rhinvoice.domain.tax.treatment import VatRules

    InvoiceCheck = Callable[[Company, Customer, Money], None]
    """Raise a ValidationError when an invoice lacks what the country requires."""

NOTICE_TREATMENTS = (
    TaxTreatment.REVERSE_CHARGE,
    TaxTreatment.EXPORT,
    TaxTreatment.SMALL_BUSINESS,
    TaxTreatment.EXEMPT,
    TaxTreatment.INTRA_COMMUNITY,
    TaxTreatment.GOODS_EXPORT,
)
"""Treatments that print a legal notice, in the order the settings list them."""

ENGLISH_NOTICES: Mapping[TaxTreatment, str] = {
    TaxTreatment.REVERSE_CHARGE: "Reverse charge: the recipient is liable for the VAT.",
    TaxTreatment.EXPORT: "Place of supply abroad, not subject to domestic VAT.",
    TaxTreatment.SMALL_BUSINESS: "No VAT is charged (small business scheme).",
    TaxTreatment.EXEMPT: "VAT exempt supply.",
    TaxTreatment.INTRA_COMMUNITY: "VAT exempt intra-Community supply of goods.",
    TaxTreatment.GOODS_EXPORT: "VAT exempt export delivery.",
}
"""English notices; the treatments say what applies, the same in every country."""


class NumberStyle(StrEnum):
    """How amounts are written on documents in the country's German."""

    APOSTROPHE = "apostrophe"
    """1'234.50 (Switzerland, Liechtenstein)."""
    DOT_COMMA = "dot_comma"
    """1.234,50 (Germany, Austria); imports read "1.500" as fifteen hundred."""


class PaymentCode(StrEnum):
    """The payment codes a company of the country prints on invoices."""

    SWISS_QR_BILL = "swiss_qr_bill"
    """The Swiss QR-bill payment part (CHF or EUR, Swiss or Liechtenstein IBAN)."""
    EPC = "epc"
    """The EPC QR code (GiroCode) on every euro invoice."""
    EPC_TO_EEA = "epc_to_eea"
    """The EPC QR code on euro invoices to customers in the EEA outside the VAT area."""


@dataclass(frozen=True, slots=True)
class CountryTerms:
    """The words of a country in one language of the documents."""

    tax_name: str
    """MWST, USt., VAT: in totals ("MWST 8.1 % auf …") and in the editor."""
    vat_number_label: str
    """Before the company's VAT number in the footer."""
    customer_vat_label: str
    """Before the customer's VAT number in the document head."""
    vat_number_field: str
    """The label of the company's VAT number field in the settings."""
    vat_number_hint: str
    """When the VAT number has to be on invoices, with an example."""
    small_business: str
    """The label of the small business switch, with its legal basis."""
    special_rate: str | None
    """The name of the third rate, or None where the country has none."""
    salutation: str
    """The first line of mails."""
    closing: str
    """The closing line of mails."""
    notices: Mapping[TaxTreatment, str]
    """The legal notice per treatment; treatments the country never applies are left out."""


@dataclass(frozen=True, slots=True)
class CountryProfile:
    """The country-specific rules of a company's country."""

    country: Country
    vat: VatRules
    """The VAT law and VAT area: decides domestic, reverse charge and export."""
    rates: tuple[TaxRateSet, ...]
    """Dated rate sets, oldest first; the rate on the date of supply applies."""
    terms: Mapping[Language, CountryTerms]
    """Words per document language; every language of Rhinvoice is required."""
    check_invoice: InvoiceCheck
    """What an invoice must state (company and customer details), checked when issuing."""
    number_style: NumberStyle
    payment_codes: frozenset[PaymentCode]
    default_currency: Currency
    cash_rounding: bool
    """Whether rounding CHF totals to 0.05 is offered (Swiss practice)."""
    tax_number: bool
    """Whether the national tax number can stand in for the VAT ID (German Steuernummer)."""
    sources: tuple[str, ...]
    """Official sources of the rules above (law texts, tax administration pages)."""

    def rates_on(self, on: date) -> TaxRateSet:
        """Return the rates that apply on the date of supply ``on``."""
        return rate_set_on(self.rates, on)

    @property
    def notice_treatments(self) -> tuple[TaxTreatment, ...]:
        """Treatments with a notice in this country (e.g. no intra-Community supply in CH)."""
        notices = self.terms[Language.DE].notices
        return tuple(treatment for treatment in NOTICE_TREATMENTS if treatment in notices)

    def notice(self, treatment: TaxTreatment, language: Language) -> str:
        """Return the built-in notice, or "" for treatments that need none (domestic VAT)."""
        return self.terms[language].notices.get(treatment, "")
