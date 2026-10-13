"""The Swiss VAT area: Switzerland and Liechtenstein share VAT law, rates and wording.

Liechtenstein applies the Swiss VAT law through the customs treaty (Zollvertrag).
Sources (checked 2026-10):

- Rates: ESTV, "MWST-Sätze ab 1. Januar 2024" (8.1 / 2.6 / 3.8 %); 2018-2023:
  7.7 / 2.5 / 3.7 %; 2011-2017: 8 / 2.5 / 3.8 % (ESTV, "Entwicklung der MWST-Sätze").
  Liechtenstein: Steuerverwaltung, identical under the treaty.
- Invoices: Art. 26 Abs. 2 lit. a MWSTG, the number under which the supplier is
  registered (UID).
- Services to EU businesses: no Swiss wording is required; the recipient's country
  asks for the reverse charge note (Art. 219a(1) VAT Directive, OPEN_QUESTIONS 8).
- Export deliveries: Art. 23 Abs. 2 Ziff. 1 MWSTG.

Not tax advice.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from rhinvoice.domain.country.profile import ENGLISH_NOTICES, CountryTerms
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.tax.rates import TaxRateSet
from rhinvoice.domain.tax.treatment import TaxTreatment, VatRules, VatSystem

if TYPE_CHECKING:
    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.customer.customer import Customer
    from rhinvoice.domain.shared.money import Money

SWISS_VAT = VatRules(VatSystem.SWISS, frozenset({"CH", "LI"}))

SWISS_RATES = (
    # Kept for imports from older programs and documents with a supply before 2018.
    TaxRateSet(date(2011, 1, 1), date(2017, 12, 31), Decimal(8), Decimal("2.5"), Decimal("3.8")),
    TaxRateSet(
        date(2018, 1, 1), date(2023, 12, 31), Decimal("7.7"), Decimal("2.5"), Decimal("3.7")
    ),
    TaxRateSet(date(2024, 1, 1), None, Decimal("8.1"), Decimal("2.6"), Decimal("3.8")),
)

SWISS_SOURCES = (
    "https://www.estv.admin.ch/estv/de/home/mehrwertsteuer/mwst-steuersaetze.html",
    "https://www.fedlex.admin.ch/eli/cc/2009/615/de (MWSTG Art. 23, 26, 39 to 41)",
    "https://www.llv.li/de/unternehmen/steuern/mehrwertsteuer",
)

_GERMAN_NOTICES = {
    # A tax advisor asks for "Übergang der Steuerschuld"; German customers need the
    # wording of § 14a Abs. 5 UStG as well (Art. 219a(1) VAT Directive: the rules of the
    # customer's country apply to suppliers outside the EU).
    TaxTreatment.REVERSE_CHARGE: (
        "Übergang der Steuerschuld auf den Leistungsempfänger "
        "(Steuerschuldnerschaft des Leistungsempfängers, Reverse Charge)."
    ),
    TaxTreatment.EXPORT: "Ort der Leistung im Ausland, nicht der MWST unterstellt.",
    TaxTreatment.SMALL_BUSINESS: "Nicht mehrwertsteuerpflichtig.",
    TaxTreatment.EXEMPT: "Von der Mehrwertsteuer befreite Leistung.",
    TaxTreatment.GOODS_EXPORT: "Steuerbefreite Ausfuhrlieferung (Art. 23 Abs. 2 Ziff. 1 MWSTG).",
}
"""Goods leave the Swiss VAT area as exports: there is no intra-Community supply."""


SWISS_TERMS = {
    Language.DE: CountryTerms(
        tax_name="MWST",
        vat_number_label="MWST-Nr.",
        customer_vat_label="Ihre UID",
        vat_number_field="UID / MWST-Nummer",
        vat_number_hint=(
            "Pflicht auf Rechnungen, wenn die Firma MWST-pflichtig ist, z. B. CHE-123.456.789 MWST."
        ),
        small_business="Nicht MWST-pflichtig (Umsatz unter CHF 100'000)",
        bad_debts="Debitorenverluste",
        write_off_hint=(
            "Bei Abrechnung nach vereinbartem Entgelt ist der Betrag eine Entgeltsminderung in "
            "der Periode, in der Sie ihn verbuchen (Art. 41 MWSTG). Bei Abrechnung nach "
            "vereinnahmtem Entgelt ist nichts zu korrigieren, das Datum dient dann nur Ihrer "
            "Übersicht."
        ),
        special_rate="Sondersatz Beherbergung",
        salutation="Guten Tag",
        closing="Freundliche Grüsse",
        notices=_GERMAN_NOTICES,
    ),
    Language.EN: CountryTerms(
        tax_name="VAT",
        vat_number_label="VAT no.",
        customer_vat_label="Your VAT no.",
        vat_number_field="UID / VAT number",
        vat_number_hint=(
            "Required on invoices of VAT registered companies, e.g. CHE-123.456.789 MWST."
        ),
        small_business="Not VAT registered (turnover below CHF 100,000)",
        bad_debts="Bad debts",
        write_off_hint=(
            "If you account for VAT by agreed consideration, the amount reduces the "
            "consideration in the period you book it (Art. 41 MWSTG). By received "
            "consideration there is nothing to correct; the date is then for your overview only."
        ),
        special_rate="Accommodation rate",
        salutation="Dear Sir or Madam",
        closing="Kind regards",
        notices={treatment: ENGLISH_NOTICES[treatment] for treatment in _GERMAN_NOTICES},
    ),
}
"""The terms of Switzerland; Liechtenstein names its VAT number differently."""


def check_swiss_invoice(company: Company, customer: Customer, total: Money) -> None:  # noqa: ARG001 - the shape of every country's check
    """VAT registered companies state their UID (Art. 26 Abs. 2 lit. a MWSTG)."""
    if not company.small_business and company.vat_number is None:
        raise ValidationError(
            "company",
            "VAT registered companies state their VAT number (UID) on invoices",
            code="company_vat_number_missing",
        )
