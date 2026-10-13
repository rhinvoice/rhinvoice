"""What every country profile must provide; a new country is complete when these pass.

See docs/adding-a-country.md.
"""

from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise

import pytest

from rhinvoice.domain.country.profile import (
    NOTICE_TREATMENTS,
    CountryProfile,
    NumberStyle,
    PaymentCode,
)
from rhinvoice.domain.country.registry import PROFILES, profile_of
from rhinvoice.domain.shared.country import Country, CountryCode
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency, Money
from rhinvoice.domain.tax.treatment import TaxTreatment, VatSystem
from rhinvoice.domain.tax.vat_number import VatNumber
from tests.unit.domain import factories

VAT_NUMBERS = {
    Country.CH: "CHE-123.456.788 MWST",
    Country.LI: "12345",
    Country.DE: "DE123456789",
    Country.AT: "ATU12345678",
}
"""A VAT number of the country's format (Liechtenstein's MWST number is kept as entered)."""

ALL = pytest.mark.parametrize("profile", list(PROFILES.values()), ids=lambda p: p.country.value)


def test_every_company_country_has_a_profile() -> None:
    assert set(PROFILES) == set(Country)
    for country, profile in PROFILES.items():
        assert profile.country is country
        assert profile_of(country) is profile


@ALL
def test_the_vat_area_holds_the_country(profile: CountryProfile) -> None:
    assert profile.country.value in profile.vat.area
    for code in profile.vat.area:
        CountryCode(code)
    if profile.vat.system is VatSystem.EU:
        assert CountryCode(profile.country.value).is_eu


@ALL
def test_rates_cover_every_day_since_the_first(profile: CountryProfile) -> None:
    assert profile.rates
    for previous, following in pairwise(profile.rates):
        assert previous.valid_to is not None
        assert following.valid_from == previous.valid_to + timedelta(days=1)
    assert profile.rates[-1].valid_to is None
    for rate_set in profile.rates:
        assert Decimal(0) < rate_set.reduced < rate_set.standard < Decimal(100)
    assert profile.rates_on(date(2100, 1, 1)) is profile.rates[-1]


@ALL
def test_the_third_rate_has_a_name_exactly_when_it_exists(profile: CountryProfile) -> None:
    special = {rate_set.special is not None for rate_set in profile.rates}
    assert len(special) == 1, "a third rate exists in every period or in none"
    exists = special.pop()
    for terms in profile.terms.values():
        assert (terms.special_rate is not None) is exists


@ALL
def test_every_language_has_every_term(profile: CountryProfile) -> None:
    assert set(profile.terms) == set(Language)
    for terms in profile.terms.values():
        for name in (
            "tax_name",
            "vat_number_label",
            "customer_vat_label",
            "vat_number_field",
            "vat_number_hint",
            "small_business",
            "bad_debts",
            "write_off_hint",
            "salutation",
            "closing",
        ):
            assert getattr(terms, name).strip(), name


@ALL
def test_every_treatment_the_country_applies_has_a_notice(profile: CountryProfile) -> None:
    expected = set(NOTICE_TREATMENTS)
    if profile.vat.system is VatSystem.SWISS:
        # Goods leave the Swiss VAT area as exports, never as intra-Community supplies.
        expected.discard(TaxTreatment.INTRA_COMMUNITY)
    for terms in profile.terms.values():
        assert set(terms.notices) == expected
        assert all(text.strip() for text in terms.notices.values())
    assert set(profile.notice_treatments) == expected
    assert profile.notice(TaxTreatment.DOMESTIC, Language.DE) == ""


@ALL
def test_payment_codes_fit_the_currency(profile: CountryProfile) -> None:
    assert profile.payment_codes
    assert not {PaymentCode.EPC, PaymentCode.EPC_TO_EEA} <= profile.payment_codes
    if PaymentCode.EPC in profile.payment_codes:
        assert profile.default_currency is Currency.EUR
    if PaymentCode.SWISS_QR_BILL in profile.payment_codes or profile.cash_rounding:
        assert profile.default_currency is Currency.CHF


@ALL
def test_sources_are_official_links(profile: CountryProfile) -> None:
    assert profile.sources
    for source in profile.sources:
        assert source.startswith("https://"), source


@ALL
def test_a_complete_company_can_invoice(profile: CountryProfile) -> None:
    company = factories.company(
        address=factories.address(country=CountryCode(profile.country.value)),
        default_currency=profile.default_currency,
        vat_number=VatNumber.parse(VAT_NUMBERS[profile.country]),
    )
    customer = factories.customer(
        address=factories.address(country=CountryCode(profile.country.value))
    )
    profile.check_invoice(company, customer, Money(Decimal(100), profile.default_currency))


def test_number_styles() -> None:
    assert profile_of(Country.CH).number_style is NumberStyle.APOSTROPHE
    assert profile_of(Country.DE).number_style is NumberStyle.DOT_COMMA


@ALL
def test_the_write_off_hint_names_its_legal_basis(profile: CountryProfile) -> None:
    basis = {
        Country.CH: "Art. 41 MWSTG",
        Country.LI: "Art. 41 MWSTG",
        Country.DE: "§ 17 Abs. 2 Nr. 1 UStG",
        Country.AT: "§ 16 Abs. 3 Z 1 UStG",
    }[profile.country]
    for terms in profile.terms.values():
        assert basis in terms.write_off_hint


def test_the_countries_name_bad_debts_in_their_own_words() -> None:
    words = {
        country: profile_of(country).terms[Language.DE].bad_debts for country in Country
    }
    assert words == {
        Country.CH: "Debitorenverluste",
        Country.LI: "Debitorenverluste",
        Country.DE: "Forderungsausfälle",
        Country.AT: "Forderungsausfälle",
    }
