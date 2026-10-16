"""Liechtenstein: the Swiss VAT area under the customs treaty, with QR-bill and CHF.

Sources: see :mod:`rhinvoice.domain.country.swiss`. Not tax advice.
"""

# ruff: noqa: RUF001 - Italian elides with the typographic apostrophe.
from __future__ import annotations

from dataclasses import replace

from rhinvoice.domain.country.profile import CountryProfile, NumberStyle, PaymentCode
from rhinvoice.domain.country.swiss import (
    SWISS_RATES,
    SWISS_SOURCES,
    SWISS_TERMS,
    SWISS_VAT,
    check_swiss_invoice,
)
from rhinvoice.domain.shared.country import Country
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency

_TERMS = {
    Language.DE: replace(
        SWISS_TERMS[Language.DE],
        vat_number_field="MWST-Nummer",
        vat_number_hint="Pflicht auf Rechnungen, wenn die Firma MWST-pflichtig ist.",
    ),
    Language.EN: replace(
        SWISS_TERMS[Language.EN],
        vat_number_field="VAT number",
        vat_number_hint="Required on invoices of VAT registered companies.",
    ),
    Language.FR: replace(
        SWISS_TERMS[Language.FR],
        vat_number_field="Numéro TVA",
        vat_number_hint="Obligatoire sur les factures des entreprises assujetties à la TVA.",
    ),
    Language.IT: replace(
        SWISS_TERMS[Language.IT],
        vat_number_field="Numero IVA",
        vat_number_hint="Obbligatorio sulle fatture delle imprese assoggettate all’IVA.",
    ),
}
"""The Swiss terms; the MWST number of Liechtenstein is not a Swiss UID."""

PROFILE = CountryProfile(
    country=Country.LI,
    vat=SWISS_VAT,
    rates=SWISS_RATES,
    terms=_TERMS,
    check_invoice=check_swiss_invoice,
    number_style=NumberStyle.APOSTROPHE,
    payment_codes=frozenset({PaymentCode.SWISS_QR_BILL, PaymentCode.EPC_TO_EEA}),
    default_currency=Currency.CHF,
    cash_rounding=True,
    tax_number=False,
    sources=SWISS_SOURCES,
)
