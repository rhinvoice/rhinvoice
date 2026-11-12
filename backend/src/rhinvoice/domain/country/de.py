"""Germany: the EU VAT Directive as applied by the UStG, EPC QR code, EUR.

Sources (checked 2026-10):

- Rates: § 12 UStG (19 / 7 %); temporarily 16 / 5 % from 2020-07-01 to 2020-12-31
  (Zweites Corona-Steuerhilfegesetz).
- Invoices: § 14 Abs. 4 Nr. 2 UStG, the tax number or the VAT ID; not for invoices
  up to EUR 250 gross (§ 33 UStDV). Small businesses state it as well (§ 34a UStDV).
- Reverse charge: § 14a Abs. 5 UStG requires "Steuerschuldnerschaft des
  Leistungsempfängers".
- Small business: since 2025 the invoice states that § 19 UStG applies.
- Intra-Community supply: § 14a Abs. 3 UStG; export delivery: § 4 Nr. 1 lit. a, § 6 UStG.
- French and Italian (ADR 0027): the mentions of the VAT Directive in its French and
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
from rhinvoice.domain.tax.presets import RatePreset
from rhinvoice.domain.tax.rates import TaxRateSet
from rhinvoice.domain.tax.tax_rate import RateCategory, RateValue
from rhinvoice.domain.tax.treatment import TaxTreatment, VatRules, VatSystem

if TYPE_CHECKING:
    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.customer.customer import Customer
    from rhinvoice.domain.shared.money import Money

SMALL_AMOUNT = Decimal(250)
"""Invoices up to this gross amount in EUR need no tax number (§ 33 UStDV)."""

_NOTICES = {
    TaxTreatment.REVERSE_CHARGE: "Steuerschuldnerschaft des Leistungsempfängers.",
    TaxTreatment.EXPORT: "Nicht im Inland steuerbare Leistung.",
    TaxTreatment.SMALL_BUSINESS: (
        "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet (Kleinunternehmerregelung)."
    ),
    TaxTreatment.EXEMPT: "Steuerfreie Leistung.",
    TaxTreatment.INTRA_COMMUNITY: (
        "Steuerfreie innergemeinschaftliche Lieferung (§ 4 Nr. 1 Buchst. b i. V. m. § 6a UStG)."
    ),
    TaxTreatment.GOODS_EXPORT: (
        "Steuerfreie Ausfuhrlieferung (§ 4 Nr. 1 Buchst. a i. V. m. § 6 UStG)."
    ),
}

_FRENCH_NOTICES = {
    TaxTreatment.REVERSE_CHARGE: "Autoliquidation.",
    TaxTreatment.EXPORT: "Prestation non soumise à la TVA en Allemagne.",
    TaxTreatment.SMALL_BUSINESS: (
        "Aucune TVA n’est facturée en vertu du § 19 UStG (franchise pour les petites entreprises)."
    ),
    TaxTreatment.EXEMPT: "Prestation exonérée.",
    TaxTreatment.INTRA_COMMUNITY: (
        "Livraison intracommunautaire exonérée (§ 4 Nr. 1 Buchst. b i. V. m. § 6a UStG)."
    ),
    TaxTreatment.GOODS_EXPORT: (
        "Livraison à l’exportation exonérée (§ 4 Nr. 1 Buchst. a i. V. m. § 6 UStG)."
    ),
}

_ITALIAN_NOTICES = {
    TaxTreatment.REVERSE_CHARGE: "Inversione contabile.",
    TaxTreatment.EXPORT: "Prestazione non soggetta all’IVA in Germania.",
    TaxTreatment.SMALL_BUSINESS: (
        "Nessuna IVA addebitata ai sensi del § 19 UStG (franchigia per le piccole imprese)."
    ),
    TaxTreatment.EXEMPT: "Prestazione esente.",
    TaxTreatment.INTRA_COMMUNITY: (
        "Cessione intracomunitaria esente (§ 4 Nr. 1 Buchst. b i. V. m. § 6a UStG)."
    ),
    TaxTreatment.GOODS_EXPORT: (
        "Cessione all’esportazione esente (§ 4 Nr. 1 Buchst. a i. V. m. § 6 UStG)."
    ),
}


def check_invoice(company: Company, customer: Customer, total: Money) -> None:  # noqa: ARG001 - the shape of every country's check
    """Require the tax number or the VAT ID above EUR 250 (§ 14 Abs. 4 UStG, § 33 UStDV)."""
    small = total.currency is Currency.EUR and total.amount <= SMALL_AMOUNT
    if company.vat_number is None and not company.tax_number and not small:
        raise ValidationError(
            "company",
            "invoices state the tax number or the VAT ID of the company",
            code="company_tax_id_missing",
        )


_AVERAGE_RATE_SOURCES = (
    "https://www.gesetze-im-internet.de/ustg_1980/__24.html (Abs. 1 Satz 1 Nr. 1 to 3, Satz 4)",
    "BGBl. 2024 I Nr. 387, Art. 25 (Nr. 3: 7,8 Prozent from 2025-01-01)",
)
_AVERAGE_RATE_NOTICE = {
    Language.DE: "Besteuerung nach Durchschnittssätzen (§ 24 UStG)",
    Language.EN: "Taxed at average rates (§ 24 UStG)",
    Language.FR: "Imposition selon les taux moyens (§ 24 UStG)",
    Language.IT: "Imposizione secondo le aliquote medie (§ 24 UStG)",
}
"""§ 24 Abs. 1 Satz 4 UStG: the invoice states the average rate; the line shows it, the notice
names the scheme."""
# Only the values of the law in force since 2025 (earlier ones changed several times); users
# add older values to their rate where they need them.
_SINCE_2025 = date(2025, 1, 1)


def _average_rate(key: str, percent: str, names: tuple[str, str, str, str]) -> RatePreset:
    return RatePreset(
        key,
        dict(zip((Language.DE, Language.EN, Language.FR, Language.IT), names, strict=True)),
        RateCategory.STANDARD,
        (RateValue(_SINCE_2025, Decimal(percent)),),
        notices=_AVERAGE_RATE_NOTICE,
        sources=_AVERAGE_RATE_SOURCES,
    )


AVERAGE_RATES = (
    _average_rate(
        "de_24_forestry",
        "5.5",
        (
            "Forstwirtschaft § 24 (5,5 %)",
            "Forestry § 24 (5.5 %)",
            "Sylviculture § 24 (5,5 %)",
            "Silvicoltura § 24 (5,5 %)",
        ),
    ),
    _average_rate(
        "de_24_beverages",
        "19",
        (
            "Getränke, Sägewerkserzeugnisse § 24 (19 %)",
            "Beverages, sawmill products § 24 (19 %)",
            "Boissons, produits de scierie § 24 (19 %)",
            "Bevande, prodotti di segheria § 24 (19 %)",
        ),
    ),
    _average_rate(
        "de_24_other",
        "7.8",
        (
            "Landwirtschaft § 24 (7,8 %)",
            "Agriculture § 24 (7.8 %)",
            "Agriculture § 24 (7,8 %)",
            "Agricoltura § 24 (7,8 %)",
        ),
    ),
)
"""§ 24 UStG average rates for farmers and foresters (#80)."""

PROFILE = CountryProfile(
    country=Country.DE,
    vat=VatRules(VatSystem.EU, frozenset({"DE"})),
    rates=(
        TaxRateSet(date(2007, 1, 1), date(2020, 6, 30), Decimal(19), Decimal(7), None),
        TaxRateSet(date(2020, 7, 1), date(2020, 12, 31), Decimal(16), Decimal(5), None),
        TaxRateSet(date(2021, 1, 1), None, Decimal(19), Decimal(7), None),
    ),
    terms={
        Language.DE: CountryTerms(
            tax_name="USt.",
            vat_number_label="USt-IdNr.",
            customer_vat_label="Ihre USt-IdNr.",
            vat_number_field="USt-IdNr.",
            vat_number_hint="Oder die Steuernummer: eine der beiden muss auf der Rechnung stehen.",
            small_business="Kleinunternehmer nach § 19 UStG",
            bad_debts="Forderungsausfälle",
            write_off_hint=(
                "Bei Soll-Versteuerung berichtigen Sie die Umsatzsteuer in dem Zeitraum, in dem "
                "die Forderung uneinbringlich wurde, und erneut, wenn doch noch gezahlt wird "
                "(§ 17 Abs. 2 Nr. 1 UStG). Das Datum ist der Tag, an dem sie uneinbringlich "
                "wurde. Bei Ist-Versteuerung und als Kleinunternehmer ist nichts zu berichtigen."
            ),
            special_rate=None,
            salutation="Guten Tag",
            closing="Mit freundlichen Grüßen",
            notices=_NOTICES,
        ),
        Language.EN: CountryTerms(
            tax_name="VAT",
            vat_number_label="VAT no.",
            customer_vat_label="Your VAT no.",
            vat_number_field="VAT ID",
            vat_number_hint="Or the tax number: one of both must be on the invoice.",
            small_business="Small business (§ 19 UStG)",
            bad_debts="Bad debts",
            write_off_hint=(
                "If you pay VAT when invoicing, correct it in the period in which the amount "
                "became uncollectible, and again if it is paid after all (§ 17 Abs. 2 Nr. 1 "
                "UStG). The date is the day it became uncollectible. If you pay VAT on receipt "
                "or are a small business, there is nothing to correct."
            ),
            special_rate=None,
            salutation="Dear Sir or Madam",
            closing="Kind regards",
            notices=ENGLISH_NOTICES,
        ),
        Language.FR: CountryTerms(
            tax_name="TVA",
            vat_number_label="N° TVA",
            customer_vat_label="Votre N° TVA",
            vat_number_field="N° d’identification TVA",
            vat_number_hint="Ou le numéro fiscal : l’un des deux doit figurer sur la facture.",
            small_business="Petite entreprise (§ 19 UStG)",
            bad_debts="Créances irrécouvrables",
            write_off_hint=(
                "Si vous déclarez la TVA à la facturation, corrigez-la dans la période où le "
                "montant est devenu irrécouvrable, et à nouveau s’il est finalement payé "
                "(§ 17 Abs. 2 Nr. 1 UStG). La date est le jour où il est devenu irrécouvrable. "
                "Si vous déclarez la TVA à l’encaissement ou êtes une petite entreprise, "
                "il n’y a rien à corriger."
            ),
            special_rate=None,
            salutation="Bonjour",
            closing="Meilleures salutations",
            notices=_FRENCH_NOTICES,
        ),
        Language.IT: CountryTerms(
            tax_name="IVA",
            vat_number_label="N. IVA",
            customer_vat_label="Vostro N. IVA",
            vat_number_field="N. di identificazione IVA",
            vat_number_hint="Oppure il numero fiscale: uno dei due deve figurare sulla fattura.",
            small_business="Piccola impresa (§ 19 UStG)",
            bad_debts="Crediti inesigibili",
            write_off_hint=(
                "Se versate l’IVA alla fatturazione, correggetela nel periodo in cui l’importo "
                "è diventato inesigibile, e di nuovo se viene comunque pagato (§ 17 Abs. 2 "
                "Nr. 1 UStG). La data è il giorno in cui è diventato inesigibile. Se versate "
                "l’IVA all’incasso o siete una piccola impresa, non c’è nulla da correggere."
            ),
            special_rate=None,
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
    tax_number=True,
    sources=(
        "https://www.gesetze-im-internet.de/ustg_1980/__12.html",
        "https://www.gesetze-im-internet.de/ustg_1980/__14.html",
        "https://www.gesetze-im-internet.de/ustg_1980/__14a.html",
        "https://www.gesetze-im-internet.de/ustdv_1980/__33.html",
        "https://www.gesetze-im-internet.de/ustg_1980/__17.html",
        "https://eur-lex.europa.eu/eli/dir/2010/45/oj (art. 226, 11 bis, French and Italian)",
        "https://eur-lex.europa.eu/eli/dir/2020/285/oj (art. 284, French and Italian)",
    ),
    scheme_presets=AVERAGE_RATES,
)
