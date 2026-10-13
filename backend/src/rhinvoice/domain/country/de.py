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

Not tax advice.
"""

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


def check_invoice(company: Company, customer: Customer, total: Money) -> None:  # noqa: ARG001 - the shape of every country's check
    """Require the tax number or the VAT ID above EUR 250 (§ 14 Abs. 4 UStG, § 33 UStDV)."""
    small = total.currency is Currency.EUR and total.amount <= SMALL_AMOUNT
    if company.vat_number is None and not company.tax_number and not small:
        raise ValidationError(
            "company",
            "invoices state the tax number or the VAT ID of the company",
            code="company_tax_id_missing",
        )


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
    ),
)
