from datetime import date
from decimal import Decimal
from itertools import pairwise

import pytest

from rhinvoice.domain.country.registry import PROFILES, profile_of
from rhinvoice.domain.shared.country import Country, CountryCode
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.treatment import (
    TaxContext,
    TaxTreatment,
    determine_treatment,
    goods_treatment,
    vat_number_would_reverse_charge,
)
from rhinvoice.domain.tax.vat_code import VatCode, vat_code


@pytest.mark.parametrize(
    ("country", "on", "standard", "reduced", "special"),
    [
        (Country.CH, date(2024, 1, 1), "8.1", "2.6", "3.8"),
        (Country.CH, date(2023, 12, 31), "7.7", "2.5", "3.7"),
        (Country.LI, date(2026, 6, 1), "8.1", "2.6", "3.8"),
        (Country.DE, date(2020, 6, 30), "19", "7", None),
        (Country.DE, date(2020, 7, 1), "16", "5", None),
        (Country.DE, date(2020, 12, 31), "16", "5", None),
        (Country.DE, date(2021, 1, 1), "19", "7", None),
        (Country.AT, date(2026, 1, 1), "20", "10", "13"),
    ],
)
def test_rates_on_date_of_supply(
    country: Country,
    on: date,
    standard: str,
    reduced: str,
    special: str | None,
) -> None:
    rates = profile_of(country).rates_on(on)
    assert rates.rate(TaxCategory.STANDARD) == Decimal(standard)
    assert rates.rate(TaxCategory.REDUCED) == Decimal(reduced)
    assert rates.rate(TaxCategory.ZERO) == 0
    assert rates.rate(TaxCategory.EXEMPT) == 0
    if special is None:
        with pytest.raises(ValidationError) as error:
            rates.rate(TaxCategory.SPECIAL)
        assert error.value.details == {
            "tax_category": "this tax rate does not exist in the country"
        }
    else:
        assert rates.rate(TaxCategory.SPECIAL) == Decimal(special)


def test_unknown_dates_are_rejected() -> None:
    with pytest.raises(ValidationError) as error:
        profile_of(Country.CH).rates_on(date(2017, 12, 31))
    assert error.value.details == {"service_date": "no VAT rates known on 2017-12-31"}


def test_rate_periods_are_contiguous() -> None:
    for periods in (profile.rates for profile in PROFILES.values()):
        for previous, following in pairwise(periods):
            assert previous.valid_to is not None
            assert (following.valid_from - previous.valid_to).days == 1
        assert periods[-1].valid_to is None


def context(
    company: str,
    customer: str,
    *,
    business: bool = True,
    vat: bool = True,
    delivery: str | None = None,
    **flags: bool,
) -> TaxContext:
    return TaxContext(
        delivery_country=None if delivery is None else CountryCode(delivery),
        company_rules=profile_of(Country(company)).vat,
        company_small_business=flags.get("small", False),
        customer_country=CountryCode(customer),
        customer_is_business=business,
        customer_has_vat_number=vat,
        customer_tax_exempt=flags.get("exempt", False),
    )


@pytest.mark.parametrize(
    ("ctx", "expected"),
    [
        (context("CH", "CH"), TaxTreatment.DOMESTIC),
        (context("CH", "LI"), TaxTreatment.DOMESTIC),
        (context("LI", "CH"), TaxTreatment.DOMESTIC),
        (context("CH", "DE"), TaxTreatment.REVERSE_CHARGE),
        (context("LI", "AT"), TaxTreatment.REVERSE_CHARGE),
        (context("CH", "DE", vat=False), TaxTreatment.EXPORT),
        (context("CH", "AT", business=False, vat=False), TaxTreatment.EXPORT),
        (context("CH", "GB"), TaxTreatment.EXPORT),
        (context("CH", "US", business=False), TaxTreatment.EXPORT),
        (context("DE", "DE"), TaxTreatment.DOMESTIC),
        (context("DE", "AT"), TaxTreatment.REVERSE_CHARGE),
        (context("DE", "AT", vat=False), TaxTreatment.DOMESTIC),
        (context("AT", "FR", business=False), TaxTreatment.DOMESTIC),
        (context("DE", "CH"), TaxTreatment.EXPORT),
        (context("AT", "CH", business=False), TaxTreatment.DOMESTIC),
        (context("CH", "CH", small=True), TaxTreatment.SMALL_BUSINESS),
        (context("DE", "AT", small=True), TaxTreatment.SMALL_BUSINESS),
        (context("CH", "CH", exempt=True), TaxTreatment.EXEMPT),
    ],
)
def test_treatment(ctx: TaxContext, expected: TaxTreatment) -> None:
    assert determine_treatment(ctx) is expected


@pytest.mark.parametrize(
    ("ctx", "expected"),
    [
        # Inside the VAT area goods and services are taxed alike.
        (context("CH", "CH"), TaxTreatment.DOMESTIC),
        (context("CH", "LI"), TaxTreatment.DOMESTIC),
        (context("DE", "DE"), TaxTreatment.DOMESTIC),
        # Goods leaving Switzerland are exports, also for EU businesses with a VAT number:
        # the customer pays import VAT at the border, there is no reverse charge.
        (context("CH", "DE"), TaxTreatment.GOODS_EXPORT),
        (context("LI", "AT", vat=False), TaxTreatment.GOODS_EXPORT),
        (context("CH", "US", business=False), TaxTreatment.GOODS_EXPORT),
        # Within the EU, to a business with a VAT number: intra-Community supply.
        (context("DE", "AT"), TaxTreatment.INTRA_COMMUNITY),
        (context("AT", "FR"), TaxTreatment.INTRA_COMMUNITY),
        # Private customers and businesses without a VAT number in the EU: domestic VAT.
        (context("DE", "AT", vat=False), TaxTreatment.DOMESTIC),
        (context("AT", "FR", business=False), TaxTreatment.DOMESTIC),
        # Out of the EU: an export delivery, for private customers too.
        (context("DE", "CH"), TaxTreatment.GOODS_EXPORT),
        (context("AT", "CH", business=False), TaxTreatment.GOODS_EXPORT),
        (context("DE", "US", business=False, vat=False), TaxTreatment.GOODS_EXPORT),
        (context("CH", "CH", small=True), TaxTreatment.SMALL_BUSINESS),
        (context("DE", "CH", small=True), TaxTreatment.SMALL_BUSINESS),
        (context("DE", "AT", exempt=True), TaxTreatment.EXEMPT),
        # The delivery address decides: goods for an Austrian business delivered in Munich
        # never leave Germany, nor do a Swiss customer's goods delivered in Germany.
        (context("DE", "AT", delivery="DE"), TaxTreatment.DOMESTIC),
        (context("DE", "CH", business=False, delivery="DE"), TaxTreatment.DOMESTIC),
        (context("DE", "DE", delivery="AT"), TaxTreatment.INTRA_COMMUNITY),
        (context("AT", "AT", delivery="CH"), TaxTreatment.GOODS_EXPORT),
        (context("CH", "DE", delivery="LI"), TaxTreatment.DOMESTIC),
        (context("LI", "LI", delivery="AT"), TaxTreatment.GOODS_EXPORT),
    ],
)
def test_goods(ctx: TaxContext, expected: TaxTreatment) -> None:
    assert goods_treatment(determine_treatment(ctx), ctx, overridden=False) is expected


@pytest.mark.parametrize(
    ("ctx", "chosen", "expected"),
    [
        # A treatment chosen by hand also applies to goods ...
        (context("AT", "CH", business=False), TaxTreatment.DOMESTIC, TaxTreatment.DOMESTIC),
        (context("DE", "AT"), TaxTreatment.EXEMPT, TaxTreatment.EXEMPT),
        # ... in its form for goods.
        (context("DE", "AT", vat=False), TaxTreatment.REVERSE_CHARGE, TaxTreatment.INTRA_COMMUNITY),
        (context("CH", "AT"), TaxTreatment.REVERSE_CHARGE, TaxTreatment.GOODS_EXPORT),
        (context("DE", "DE"), TaxTreatment.EXPORT, TaxTreatment.GOODS_EXPORT),
        # A domestic reverse charge (e.g. § 13b Abs. 2 Nr. 7 UStG, scrap) stays one.
        (context("DE", "DE"), TaxTreatment.REVERSE_CHARGE, TaxTreatment.REVERSE_CHARGE),
        (context("CH", "LI"), TaxTreatment.REVERSE_CHARGE, TaxTreatment.REVERSE_CHARGE),
        (
            context("DE", "AT", delivery="DE"),
            TaxTreatment.REVERSE_CHARGE,
            TaxTreatment.REVERSE_CHARGE,
        ),
        (context("DE", "US"), TaxTreatment.REVERSE_CHARGE, TaxTreatment.GOODS_EXPORT),
        (context("AT", "CH"), TaxTreatment.SMALL_BUSINESS, TaxTreatment.SMALL_BUSINESS),
    ],
)
def test_goods_follow_a_chosen_treatment(
    ctx: TaxContext, chosen: TaxTreatment, expected: TaxTreatment
) -> None:
    assert goods_treatment(chosen, ctx, overridden=True) is expected


def test_goods_treatments_are_never_chosen_for_a_whole_document() -> None:
    assert [t for t in TaxTreatment if t.goods_only] == [
        TaxTreatment.INTRA_COMMUNITY,
        TaxTreatment.GOODS_EXPORT,
    ]


def test_only_domestic_charges_vat() -> None:
    assert [t for t in TaxTreatment if t.charges_vat] == [TaxTreatment.DOMESTIC]


@pytest.mark.parametrize(
    ("ctx", "expected"),
    [
        (context("CH", "AT", vat=False), True),
        (context("DE", "AT", vat=False), True),
        (context("CH", "AT"), False),
        (context("CH", "AT", vat=False, business=False), False),
        (context("DE", "DE", vat=False), False),
        (context("CH", "US", vat=False), False),
        (context("CH", "LI", vat=False), False),
        (context("AT", "DE", vat=False, small=True), False),
        (context("AT", "DE", vat=False, exempt=True), False),
    ],
)
def test_a_missing_vat_number_is_noticed_where_it_would_reverse_charge(
    ctx: TaxContext,
    expected: bool,
) -> None:
    assert vat_number_would_reverse_charge(ctx) is expected


@pytest.mark.parametrize(
    ("treatment", "category", "code"),
    [
        (TaxTreatment.DOMESTIC, TaxCategory.STANDARD, VatCode.STANDARD),
        (TaxTreatment.DOMESTIC, TaxCategory.REDUCED, VatCode.STANDARD),
        (TaxTreatment.DOMESTIC, TaxCategory.SPECIAL, VatCode.STANDARD),
        (TaxTreatment.DOMESTIC, TaxCategory.ZERO, VatCode.ZERO),
        (TaxTreatment.DOMESTIC, TaxCategory.EXEMPT, VatCode.EXEMPT),
        (TaxTreatment.REVERSE_CHARGE, TaxCategory.STANDARD, VatCode.REVERSE_CHARGE),
        (TaxTreatment.EXPORT, TaxCategory.STANDARD, VatCode.EXPORT),
        (TaxTreatment.GOODS_EXPORT, TaxCategory.REDUCED, VatCode.EXPORT),
        (TaxTreatment.INTRA_COMMUNITY, TaxCategory.STANDARD, VatCode.INTRA_COMMUNITY),
        (TaxTreatment.SMALL_BUSINESS, TaxCategory.STANDARD, VatCode.EXEMPT),
        (TaxTreatment.EXEMPT, TaxCategory.REDUCED, VatCode.EXEMPT),
    ],
)
def test_vat_codes(treatment: TaxTreatment, category: TaxCategory, code: VatCode) -> None:
    assert vat_code(treatment, category) is code
