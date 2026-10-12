"""Switzerland: the Swiss VAT area with QR-bill, CHF and rounding to 5 centimes.

Sources: see :mod:`rhinvoice.domain.country.swiss`; QR-bill: SIX Implementation
Guidelines QR-bill 2.3. Not tax advice.
"""

from __future__ import annotations

from rhinvoice.domain.country.profile import CountryProfile, NumberStyle, PaymentCode
from rhinvoice.domain.country.swiss import (
    SWISS_RATES,
    SWISS_SOURCES,
    SWISS_TERMS,
    SWISS_VAT,
    check_swiss_invoice,
)
from rhinvoice.domain.shared.country import Country
from rhinvoice.domain.shared.money import Currency

PROFILE = CountryProfile(
    country=Country.CH,
    vat=SWISS_VAT,
    rates=SWISS_RATES,
    terms=SWISS_TERMS,
    check_invoice=check_swiss_invoice,
    number_style=NumberStyle.APOSTROPHE,
    # Euro invoices to customers in the EEA carry the EPC code as well.
    payment_codes=frozenset({PaymentCode.SWISS_QR_BILL, PaymentCode.EPC_TO_EEA}),
    default_currency=Currency.CHF,
    cash_rounding=True,
    tax_number=False,
    sources=(
        *SWISS_SOURCES,
        "https://www.six-group.com/en/products-services/banking-services/payment-standardization/standards/qr-bill.html",
    ),
)
