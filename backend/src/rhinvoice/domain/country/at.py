"""Austria: the EU VAT Directive as applied by the UStG 1994, EPC QR code, EUR.

Sources (checked 2026-10):

- Rates: § 10 UStG 1994 (20 / 10 / 13 %).
- Invoices: § 11 Abs. 1 Z 3 lit. i UStG, the VAT ID of the supplier, not for invoices
  up to EUR 400 gross (§ 11 Abs. 6) nor for small businesses; above EUR 10'000 gross
  also the VAT ID of the business customer (§ 11 Abs. 1 Z 3 lit. b), approximated as
  business customers in Austria.
- Reverse charge: § 11 Abs. 1a UStG, a reference to the transfer of the tax liability
  (https://www.wko.at/steuern/umsatzsteuer-rechnung-faq).
- Small business: § 6 Abs. 1 Z 27 UStG. Intra-Community supply: Art. 6 Abs. 1, Art. 7
  and Art. 11 Abs. 2 UStG (Binnenmarktregelung); export delivery: § 6 Abs. 1 Z 1, § 7 UStG.
- French and Italian (ADR 0026): the mentions of the VAT Directive in its French and
  Italian version: "Autoliquidation" / "inversione contabile" (Art. 226 point 11a),
  "franchise pour les petites entreprises" / "franchigia per le piccole imprese"
  (Art. 284, Directive (EU) 2020/285), exempt supplies "exonérée" / "esente"
  (Art. 226 point 11); the national provision stays as the law cites it.

Not tax advice.
"""

# ruff: noqa: RUF001 - French and Italian elide with the typographic apostrophe.
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from rhinvoice.domain.country.profile import (
    ENGLISH_NOTICES,
    CountryProfile,
    CountryTerms,
    NumberStyle,
    PaymentCode,
)
from rhinvoice.domain.shared.country import Country
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from rhinvoice.domain.tax.rates import TaxRateSet
from rhinvoice.domain.tax.treatment import TaxTreatment, VatRules, VatSystem

if TYPE_CHECKING:
    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.customer.customer import Customer
    from rhinvoice.domain.shared.money import Money

SMALL_AMOUNT = Decimal(400)
"""Invoices up to this gross amount in EUR need no VAT ID of the company (§ 11 Abs. 6)."""
CUSTOMER_VAT_THRESHOLD = Decimal(10_000)
"""Above this gross amount in EUR the business customer's VAT ID is required."""

_NOTICES = {
    TaxTreatment.REVERSE_CHARGE: (
        "Übergang der Steuerschuld auf den Leistungsempfänger (Reverse Charge)."
    ),
    TaxTreatment.EXPORT: "Nicht im Inland steuerbare Leistung.",
    TaxTreatment.SMALL_BUSINESS: (
        "Umsatzsteuerfrei aufgrund der Kleinunternehmerregelung (§ 6 Abs. 1 Z 27 UStG)."
    ),
    TaxTreatment.EXEMPT: "Steuerfreie Leistung.",
    TaxTreatment.INTRA_COMMUNITY: (
        "Steuerfreie innergemeinschaftliche Lieferung (Art. 6 Abs. 1 i. V. m. Art. 7 UStG)."
    ),
    TaxTreatment.GOODS_EXPORT: ("Steuerfreie Ausfuhrlieferung (§ 6 Abs. 1 Z 1 i. V. m. § 7 UStG)."),
}

_FRENCH_NOTICES = {
    TaxTreatment.REVERSE_CHARGE: "Autoliquidation.",
    TaxTreatment.EXPORT: "Prestation non soumise à la TVA en Autriche.",
    TaxTreatment.SMALL_BUSINESS: (
        "Exonéré de la TVA en vertu de la franchise pour les petites entreprises "
        "(§ 6 Abs. 1 Z 27 UStG)."
    ),
    TaxTreatment.EXEMPT: "Prestation exonérée.",
    TaxTreatment.INTRA_COMMUNITY: (
        "Livraison intracommunautaire exonérée (Art. 6 Abs. 1 i. V. m. Art. 7 UStG)."
    ),
    TaxTreatment.GOODS_EXPORT: (
        "Livraison à l’exportation exonérée (§ 6 Abs. 1 Z 1 i. V. m. § 7 UStG)."
    ),
}

_ITALIAN_NOTICES = {
    TaxTreatment.REVERSE_CHARGE: "Inversione contabile.",
    TaxTreatment.EXPORT: "Prestazione non soggetta all’IVA in Austria.",
    TaxTreatment.SMALL_BUSINESS: (
        "Esente da IVA in virtù della franchigia per le piccole imprese (§ 6 Abs. 1 Z 27 UStG)."
    ),
    TaxTreatment.EXEMPT: "Prestazione esente.",
    TaxTreatment.INTRA_COMMUNITY: (
        "Cessione intracomunitaria esente (Art. 6 Abs. 1 i. V. m. Art. 7 UStG)."
    ),
    TaxTreatment.GOODS_EXPORT: (
        "Cessione all’esportazione esente (§ 6 Abs. 1 Z 1 i. V. m. § 7 UStG)."
    ),
}


def _euros_above(total: Money, limit: Decimal) -> bool:
    """Amount limits are in euros; other currencies never count as small amounts."""
    return total.currency is not Currency.EUR or total.amount > limit


def check_invoice(company: Company, customer: Customer, total: Money) -> None:
    """Require the company's VAT ID above EUR 400, the customer's above EUR 10'000 (§ 11)."""
    if company.small_business:
        return
    if company.vat_number is None and _euros_above(total, SMALL_AMOUNT):
        raise ValidationError(
            "company",
            "invoices above EUR 400 state the VAT ID (UID) of the company",
            code="company_vat_number_missing",
        )
    if (
        customer.is_business
        and customer.address.country.value == Country.AT.value
        and customer.vat_number is None
        and _euros_above(total, CUSTOMER_VAT_THRESHOLD)
    ):
        raise ValidationError(
            "customer_id",
            "invoices above EUR 10'000 state the VAT ID (UID) of the customer",
            code="customer_vat_number_required",
        )


PROFILE = CountryProfile(
    country=Country.AT,
    vat=VatRules(VatSystem.EU, frozenset({"AT"})),
    rates=(TaxRateSet(date(2016, 1, 1), None, Decimal(20), Decimal(10), Decimal(13)),),
    terms={
        Language.DE: CountryTerms(
            tax_name="USt.",
            vat_number_label="UID-Nr.",
            customer_vat_label="Ihre UID",
            vat_number_field="UID-Nummer",
            vat_number_hint="Pflicht auf Rechnungen über EUR 400, z. B. ATU12345678.",
            small_business="Kleinunternehmer nach § 6 Abs. 1 Z 27 UStG",
            bad_debts="Forderungsausfälle",
            write_off_hint=(
                "Bei Sollbesteuerung berichtigen Sie die Umsatzsteuer in dem Zeitraum, in dem "
                "die Forderung uneinbringlich wurde, und erneut, wenn doch noch gezahlt wird "
                "(§ 16 Abs. 3 Z 1 UStG). Das Datum ist der Tag, an dem sie uneinbringlich "
                "wurde. Bei Istbesteuerung und als Kleinunternehmer ist nichts zu berichtigen."
            ),
            special_rate="Zweiter ermäßigter Satz",
            salutation="Guten Tag",
            closing="Mit freundlichen Grüßen",
            notices=_NOTICES,
        ),
        Language.EN: CountryTerms(
            tax_name="VAT",
            vat_number_label="VAT no.",
            customer_vat_label="Your VAT no.",
            vat_number_field="VAT number (UID)",
            vat_number_hint="Required on invoices above EUR 400, e.g. ATU12345678.",
            small_business="Small business (§ 6 Abs. 1 Z 27 UStG)",
            bad_debts="Bad debts",
            write_off_hint=(
                "If you pay VAT when invoicing, correct it in the period in which the amount "
                "became uncollectible, and again if it is paid after all (§ 16 Abs. 3 Z 1 "
                "UStG). The date is the day it became uncollectible. If you pay VAT on receipt "
                "or are a small business, there is nothing to correct."
            ),
            special_rate="Second reduced rate",
            salutation="Dear Sir or Madam",
            closing="Kind regards",
            notices=ENGLISH_NOTICES,
        ),
        Language.FR: CountryTerms(
            tax_name="TVA",
            vat_number_label="N° TVA",
            customer_vat_label="Votre N° TVA",
            vat_number_field="Numéro TVA (UID)",
            vat_number_hint="Obligatoire sur les factures de plus de EUR 400, p. ex. ATU12345678.",
            small_business="Petite entreprise (§ 6 Abs. 1 Z 27 UStG)",
            bad_debts="Créances irrécouvrables",
            write_off_hint=(
                "Si vous déclarez la TVA à la facturation, corrigez-la dans la période où le "
                "montant est devenu irrécouvrable, et à nouveau s’il est finalement payé "
                "(§ 16 Abs. 3 Z 1 UStG). La date est le jour où il est devenu irrécouvrable. "
                "Si vous déclarez la TVA à l’encaissement ou êtes une petite entreprise, "
                "il n’y a rien à corriger."
            ),
            special_rate="Deuxième taux réduit",
            salutation="Bonjour",
            closing="Meilleures salutations",
            notices=_FRENCH_NOTICES,
        ),
        Language.IT: CountryTerms(
            tax_name="IVA",
            vat_number_label="N. IVA",
            customer_vat_label="Vostro N. IVA",
            vat_number_field="Numero IVA (UID)",
            vat_number_hint="Obbligatorio sulle fatture oltre EUR 400, p. es. ATU12345678.",
            small_business="Piccola impresa (§ 6 Abs. 1 Z 27 UStG)",
            bad_debts="Crediti inesigibili",
            write_off_hint=(
                "Se versate l’IVA alla fatturazione, correggetela nel periodo in cui l’importo "
                "è diventato inesigibile, e di nuovo se viene comunque pagato (§ 16 Abs. 3 "
                "Z 1 UStG). La data è il giorno in cui è diventato inesigibile. Se versate "
                "l’IVA all’incasso o siete una piccola impresa, non c’è nulla da correggere."
            ),
            special_rate="Seconda aliquota ridotta",
            salutation="Buongiorno",
            closing="Cordiali saluti",
            notices=_ITALIAN_NOTICES,
        ),
    },
    check_invoice=check_invoice,
    number_style=NumberStyle.DOT_COMMA,
    payment_codes=frozenset({PaymentCode.EPC}),
    default_currency=Currency.EUR,
    cash_rounding=False,
    tax_number=False,
    sources=(
        "https://www.ris.bka.gv.at/GeltendeFassung.wxe?Abfrage=Bundesnormen&Gesetzesnummer=10004873",
        "https://www.wko.at/steuern/umsatzsteuer-rechnung-faq",
        "https://eur-lex.europa.eu/eli/dir/2010/45/oj (art. 226, 11 bis, French and Italian)",
        "https://eur-lex.europa.eu/eli/dir/2020/285/oj (art. 284, French and Italian)",
    ),
)
