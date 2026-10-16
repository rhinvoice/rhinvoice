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
- French and Italian (ADR 0027): the words of the law in its French (LTVA) and Italian
  (LIVA) version: assujetti / assoggettato (Art. 10), exonérées / esenti (Art. 23), lieu
  de la prestation de services / luogo della prestazione di servizi (Art. 8),
  contre-prestations convenues / controprestazioni convenute (Art. 39); the UID-MWST
  number is written CHE-123.456.789 TVA / IVA (ESTV, numéro IDE / numero IDI); rates
  as named by the ESTV (taux spécial pour l'hébergement / aliquota speciale per il
  settore alberghiero). Services to EU businesses: the mention of Art. 226 point 11a
  VAT Directive in its French and Italian version ("Autoliquidation", "inversione
  contabile"). The law prescribes no wording for these notices.

Not tax advice.
"""

# ruff: noqa: RUF001 - French and Italian elide with the typographic apostrophe.
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
    "https://www.fedlex.admin.ch/eli/cc/2009/615/fr (LTVA art. 8, 10, 23, 39, 41)",
    "https://www.fedlex.admin.ch/eli/cc/2009/615/it (LIVA art. 8, 10, 23, 39, 41)",
    "https://www.estv.admin.ch/fr/numero-identification-des-entreprises-ide",
    "https://www.estv.admin.ch/it/numero-identificazione-delle-imprese-idi",
    "https://www.estv.admin.ch/fr/taux-de-la-tva-suisse",
    "https://www.estv.admin.ch/it/aliquote-iva-svizzere",
    "https://eur-lex.europa.eu/eli/dir/2010/45/oj (art. 226, 11 bis, French and Italian)",
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

_FRENCH_NOTICES = {
    # Art. 226 point 11a of the VAT Directive in French: the customer's country asks for it.
    TaxTreatment.REVERSE_CHARGE: (
        "Autoliquidation : la TVA est due par le destinataire de la prestation."
    ),
    TaxTreatment.EXPORT: (
        "Prestation de services non soumise à la TVA "
        "(lieu de la prestation de services à l’étranger)."
    ),
    TaxTreatment.SMALL_BUSINESS: "Non assujetti à la TVA.",
    TaxTreatment.EXEMPT: "Prestation exonérée de la TVA.",
    TaxTreatment.GOODS_EXPORT: (
        "Livraison à l’exportation exonérée de l’impôt (art. 23, al. 2, ch. 1, LTVA)."
    ),
}
"""The French notices, in the words of the LTVA."""

_ITALIAN_NOTICES = {
    # Art. 226 point 11a of the VAT Directive in Italian: the customer's country asks for it.
    TaxTreatment.REVERSE_CHARGE: (
        "Inversione contabile: l’imposta è dovuta dal destinatario della prestazione."
    ),
    TaxTreatment.EXPORT: (
        "Prestazione di servizi non soggetta all’IVA "
        "(luogo della prestazione di servizi all’estero)."
    ),
    TaxTreatment.SMALL_BUSINESS: "Non assoggettato all’IVA.",
    TaxTreatment.EXEMPT: "Prestazione esente dall’IVA.",
    TaxTreatment.GOODS_EXPORT: (
        "Fornitura all’esportazione esente dall’imposta (art. 23 cpv. 2 n. 1 LIVA)."
    ),
}
"""The Italian notices, in the words of the LIVA."""


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
    Language.FR: CountryTerms(
        tax_name="TVA",
        vat_number_label="N° TVA",
        customer_vat_label="Votre IDE",
        vat_number_field="IDE / numéro TVA",
        vat_number_hint=(
            "Obligatoire sur les factures des entreprises assujetties à la TVA, "
            "p. ex. CHE-123.456.789 TVA."
        ),
        small_business="Non assujetti à la TVA (chiffre d’affaires inférieur à 100 000 francs)",
        bad_debts="Pertes sur débiteurs",
        write_off_hint=(
            "En cas de décompte selon les contre-prestations convenues, le montant diminue la "
            "contre-prestation de la période dans laquelle vous le comptabilisez (art. 41 LTVA). "
            "En cas de décompte selon les contre-prestations reçues, il n’y a rien à corriger ; "
            "la date sert alors uniquement à votre vue d’ensemble."
        ),
        special_rate="Taux spécial pour l’hébergement",
        salutation="Bonjour",
        closing="Meilleures salutations",
        notices=_FRENCH_NOTICES,
    ),
    Language.IT: CountryTerms(
        tax_name="IVA",
        vat_number_label="N. IVA",
        customer_vat_label="Vostro IDI",
        vat_number_field="IDI / numero IVA",
        vat_number_hint=(
            "Obbligatorio sulle fatture delle imprese assoggettate all’IVA, "
            "p. es. CHE-123.456.789 IVA."
        ),
        small_business="Non assoggettato all’IVA (cifra d’affari inferiore a 100 000 franchi)",
        bad_debts="Perdite su debitori",
        write_off_hint=(
            "Con il rendiconto secondo le controprestazioni convenute, l’importo riduce la "
            "controprestazione del periodo in cui lo registrate (art. 41 LIVA). Con il "
            "rendiconto secondo le controprestazioni ricevute non c’è nulla da correggere; "
            "la data serve allora solo alla vostra panoramica."
        ),
        special_rate="Aliquota speciale per il settore alberghiero",
        salutation="Buongiorno",
        closing="Cordiali saluti",
        notices=_ITALIAN_NOTICES,
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
