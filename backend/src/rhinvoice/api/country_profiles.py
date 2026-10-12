"""The country profile of the API: what the interface shows differently per country."""

from datetime import date
from typing import Self

from rhinvoice.api.schemas import ApiModel, plain_number
from rhinvoice.domain.country.profile import CountryProfile, NumberStyle, PaymentCode
from rhinvoice.domain.shared.country import Country
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from rhinvoice.domain.tax.treatment import VatSystem


class CountryTermsResponse(ApiModel):
    tax_name: str
    vat_number_label: str
    vat_number_field: str
    vat_number_hint: str
    small_business: str
    special_rate: str | None


class RatesResponse(ApiModel):
    """Rates in percent."""

    standard: str
    reduced: str
    special: str | None
    """The third rate; None where the country has none."""


class TermsResponse(ApiModel):
    de: CountryTermsResponse
    en: CountryTermsResponse


class CountryProfileResponse(ApiModel):
    country: Country
    vat_system: VatSystem
    vat_area: list[str]
    """ISO codes inside the country's VAT area (Switzerland with Liechtenstein)."""
    rates: RatesResponse
    """The rates that apply today."""
    terms: TermsResponse
    number_style: NumberStyle
    payment_codes: list[PaymentCode]
    default_currency: Currency
    cash_rounding: bool
    """Whether rounding CHF totals to 0.05 is offered."""
    tax_number: bool
    """Whether the national tax number can stand in for the VAT ID."""

    @classmethod
    def of(cls, profile: CountryProfile, today: date) -> Self:
        rates = profile.rates_on(today)
        terms = {
            language: CountryTermsResponse(
                tax_name=terms.tax_name,
                vat_number_label=terms.vat_number_label,
                vat_number_field=terms.vat_number_field,
                vat_number_hint=terms.vat_number_hint,
                small_business=terms.small_business,
                special_rate=terms.special_rate,
            )
            for language, terms in profile.terms.items()
        }
        return cls(
            country=profile.country,
            vat_system=profile.vat.system,
            vat_area=sorted(profile.vat.area),
            rates=RatesResponse(
                standard=plain_number(rates.standard),
                reduced=plain_number(rates.reduced),
                special=None if rates.special is None else plain_number(rates.special),
            ),
            terms=TermsResponse(de=terms[Language.DE], en=terms[Language.EN]),
            number_style=profile.number_style,
            payment_codes=sorted(profile.payment_codes),
            default_currency=profile.default_currency,
            cash_rounding=profile.cash_rounding,
            tax_number=profile.tax_number,
        )
