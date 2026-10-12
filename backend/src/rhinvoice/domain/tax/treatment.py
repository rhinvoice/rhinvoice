"""How VAT is applied to a document (Steuerfall).

Determined from the company's and the customer's country and whether the
customer is a business. A manual override is possible and logged on the
document. Uncertain cases fall back to charging domestic VAT (conservative,
see OPEN_QUESTIONS.md).

The document's treatment is the one of its services. Goods cross borders
under their own rules (:func:`goods_treatment`): an EU business with a VAT
number receives them as an intra-Community supply, everything leaving the
VAT area is an export delivery. See ADR 0014.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rhinvoice.domain.shared.country import CountryCode


class VatSystem(StrEnum):
    """The VAT law a company's country follows; it decides cross-border cases."""

    EU = "eu"
    """The EU VAT Directive (2006/112/EC) as applied by a member state."""
    SWISS = "swiss"
    """The Swiss MWSTG, also applied by Liechtenstein under the customs treaty."""


@dataclass(frozen=True, slots=True)
class VatRules:
    """The VAT law of the company's country and the countries forming its VAT area."""

    system: VatSystem
    area: frozenset[str]
    """ISO codes inside the VAT area: Switzerland with Liechtenstein, else the country."""


class TaxTreatment(StrEnum):
    DOMESTIC = "domestic"
    """Normal VAT of the company's country."""
    REVERSE_CHARGE = "reverse_charge"
    """The business recipient in the EU owes the tax (Art. 196 VAT Directive).

    Intra-EU B2B supplies, and services from CH/LI to EU businesses with a VAT
    number: the place of supply is the recipient's country (Art. 44 VAT
    Directive), where the recipient accounts for the VAT.
    """
    EXPORT = "export"
    """Supply outside the VAT area: no VAT, export notice."""
    SMALL_BUSINESS = "small_business"
    """Company not VAT registered: no VAT, mandatory notice."""
    EXEMPT = "exempt"
    """Customer exempt from VAT (e.g. diplomatic missions): no VAT."""
    INTRA_COMMUNITY = "intra_community"
    """Goods to a business with a VAT number in another EU country: exempt.

    Art. 138 VAT Directive; § 4 Nr. 1 lit. b and § 6a UStG (DE), Art. 6 Abs. 1 and
    Art. 7 UStG (AT). Goods lines only.
    """
    GOODS_EXPORT = "goods_export"
    """Goods leaving the VAT area: exempt export delivery, for every customer.

    Art. 23 Abs. 2 Ziff. 1 MWSTG (CH/LI); § 4 Nr. 1 lit. a and § 6 UStG (DE);
    § 6 Abs. 1 Z 1 and § 7 UStG (AT). Goods lines only; the exemption needs proof
    of the export (customs).
    """

    @property
    def charges_vat(self) -> bool:
        return self is TaxTreatment.DOMESTIC

    @property
    def goods_only(self) -> bool:
        """Applies to goods lines only, never to a whole document."""
        return self in {TaxTreatment.INTRA_COMMUNITY, TaxTreatment.GOODS_EXPORT}


@dataclass(frozen=True, slots=True)
class TaxContext:
    company_rules: VatRules
    company_small_business: bool
    customer_country: CountryCode
    customer_is_business: bool
    customer_has_vat_number: bool
    customer_tax_exempt: bool
    delivery_country: CountryCode | None = None
    """Where goods are delivered to, when the customer has a delivery address."""

    @property
    def destination(self) -> CountryCode:
        """The country goods go to."""
        return self.delivery_country or self.customer_country


def determine_treatment(context: TaxContext) -> TaxTreatment:
    if context.company_small_business:
        return TaxTreatment.SMALL_BUSINESS
    if context.customer_tax_exempt:
        return TaxTreatment.EXEMPT
    return _by_location(context)


def _by_location(context: TaxContext) -> TaxTreatment:
    customer = context.customer_country
    if context.company_rules.system is VatSystem.SWISS:
        return _from_swiss_vat_area(context)
    if customer.value in context.company_rules.area:
        return TaxTreatment.DOMESTIC
    if customer.is_eu:
        # B2B within the EU requires the customer's VAT number; otherwise domestic VAT.
        if context.customer_is_business and context.customer_has_vat_number:
            return TaxTreatment.REVERSE_CHARGE
        return TaxTreatment.DOMESTIC
    # Third countries: B2B services are taxed where the recipient is (§ 3a para. 2 UStG DE,
    # § 3a para. 6 UStG AT). For private customers the supplier's place applies in general,
    # so domestic VAT is charged (conservative; goods exports may be exempt, see OPEN_QUESTIONS).
    return TaxTreatment.EXPORT if context.customer_is_business else TaxTreatment.DOMESTIC


def _from_swiss_vat_area(context: TaxContext) -> TaxTreatment:
    customer = context.customer_country
    if customer.value in context.company_rules.area:
        return TaxTreatment.DOMESTIC
    # Recipient principle (Art. 8 para. 1 MWSTG): no Swiss VAT abroad. EU businesses
    # with a VAT number account for it themselves (e.g. § 13b UStG DE, § 19 UStG AT),
    # so the invoice carries the reverse charge notice (see OPEN_QUESTIONS 8).
    if customer.is_eu and context.customer_is_business and context.customer_has_vat_number:
        return TaxTreatment.REVERSE_CHARGE
    return TaxTreatment.EXPORT


def _destination_inside(context: TaxContext) -> bool:
    """Whether the goods stay in the company's VAT area (CH with LI, else its country)."""
    return context.destination.value in context.company_rules.area


def goods_treatment(
    treatment: TaxTreatment, context: TaxContext, *, overridden: bool
) -> TaxTreatment:
    """Return the treatment of the goods lines of a document with ``treatment``.

    Goods follow the place they are delivered to (the customer's delivery address,
    else the customer's address), not the place of the customer:

    * staying in the company's VAT area: domestic VAT, also for foreign customers;
    * to a business with a VAT number in another EU country: intra-Community supply
      (never from CH/LI: there the customer pays import VAT);
    * leaving the EU, or from CH/LI abroad: export delivery, also to private customers;
    * to private customers in other EU countries: domestic VAT (distance sales below the
      EU-wide EUR 10'000 threshold, see OPEN_QUESTIONS).

    A treatment chosen by hand also applies to goods, in their form: reverse charge
    across a border becomes an intra-Community supply or an export, a domestic reverse
    charge (e.g. § 13b Abs. 2 Nr. 7 UStG) stays one; an export is an export delivery.
    """
    if treatment in {TaxTreatment.SMALL_BUSINESS, TaxTreatment.EXEMPT}:
        return treatment
    inside = _destination_inside(context)
    if overridden:
        if treatment is TaxTreatment.EXPORT:
            return TaxTreatment.GOODS_EXPORT
        if treatment is TaxTreatment.REVERSE_CHARGE and not inside:
            return _across_border(context, business=True)
        return treatment
    if inside:
        return TaxTreatment.DOMESTIC
    return _across_border(
        context, business=context.customer_is_business and context.customer_has_vat_number
    )


def _across_border(context: TaxContext, *, business: bool) -> TaxTreatment:
    if context.company_rules.system is VatSystem.SWISS or not context.destination.is_eu:
        return TaxTreatment.GOODS_EXPORT
    return TaxTreatment.INTRA_COMMUNITY if business else TaxTreatment.DOMESTIC


def vat_number_would_reverse_charge(context: TaxContext) -> bool:
    """Whether the customer's VAT number is missing for reverse charge.

    EU businesses without a VAT number are charged domestic VAT (DE/AT) or
    treated as an export (CH/LI); with it, they would owe the tax themselves.
    """
    if context.customer_has_vat_number:
        return False
    with_number = replace(context, customer_has_vat_number=True)
    return determine_treatment(with_number) is TaxTreatment.REVERSE_CHARGE
