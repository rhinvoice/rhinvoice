"""Document totals.

Order (CLAUDE.md §6): line → line discount → document discount → VAT grouped
per rate → rounding of the payable amount.

* Line amounts are rounded to the currency's minor unit (commercial rounding),
  so that printed lines add up to the printed total (EN 16931 BR-CO-10).
* The document discount is distributed over the VAT groups in proportion to
  their amounts (largest group absorbs the remainder).
* VAT is computed once per group on the group's amount, never per line.
* Cash rounding (CHF 0.05) applies only to the payable total.
* Goods lines may have a treatment of their own (export, intra-Community
  supply), so one document can hold taxed and exempt groups (ADR 0014).
See ADR 0005.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from rhinvoice.domain.document.lines import HUNDRED, DiscountKind, PriceMode
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.money import Money, round_half_up
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import line_treatment
from rhinvoice.domain.tax.vat_code import VatCode, vat_code

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from uuid import UUID

    from rhinvoice.domain.document.lines import Discount, DocumentLine
    from rhinvoice.domain.shared.money import Currency
    from rhinvoice.domain.tax.treatment import TaxTreatment

CASH_ROUNDING_STEP = Decimal("0.05")


@dataclass(frozen=True, slots=True)
class CalculationInput:
    currency: Currency
    price_mode: PriceMode
    lines: Sequence[DocumentLine]
    discount: Discount
    treatment: TaxTreatment
    rate_for: Callable[[DocumentLine], Decimal]
    """VAT rate of a line (the frozen rate of issued lines, the current one of drafts)."""
    cash_rounding: bool
    goods_treatment: TaxTreatment | None = None
    """Treatment of the goods lines; None: the document's treatment."""

    def treatment_of(self, line: DocumentLine) -> TaxTreatment:
        return line_treatment(line.supply, self.treatment, self.goods_treatment)


@dataclass(frozen=True, slots=True)
class LineAmount:
    line_id: UUID
    amount: Money
    """Net amount in NET mode, gross amount in GROSS mode, after the line discount."""
    vat_code: VatCode
    tax_rate: Decimal


@dataclass(frozen=True, slots=True)
class TaxGroup:
    vat_code: VatCode
    rate: Decimal
    amount: Money
    """Sum of the line amounts of this group before the document discount."""
    discount: Money
    net: Money
    tax: Money

    @property
    def gross(self) -> Money:
        return self.net + self.tax


@dataclass(frozen=True, slots=True)
class Totals:
    currency: Currency
    lines: tuple[LineAmount, ...]
    groups: tuple[TaxGroup, ...]
    subtotal: Money
    discount: Money
    net: Money
    tax: Money
    gross: Money
    rounding: Money
    """Cash rounding difference (total - gross)."""
    total: Money
    """Payable amount."""


def _group_key(line: LineAmount) -> tuple[VatCode, Decimal]:
    return (line.vat_code, line.tax_rate)


def _allocate_discount(
    amounts: list[Decimal],
    calculation: CalculationInput,
    subtotal: Decimal,
) -> list[Decimal]:
    """Discount per group, signed like the amounts (cancellations are negative)."""
    step = calculation.currency.minor_step
    discount = calculation.discount
    if discount.kind is DiscountKind.PERCENT:
        return [round_half_up(amount * discount.value / HUNDRED, step) for amount in amounts]
    if discount.value > abs(subtotal):
        raise ValidationError("discount", "the discount is larger than the document amount")
    signed = discount.value if subtotal >= 0 else -discount.value
    shares = [
        round_half_up(signed * amount / subtotal, step) if subtotal != 0 else Decimal(0)
        for amount in amounts
    ]
    largest = max(range(len(amounts)), key=lambda index: abs(amounts[index]))
    shares[largest] += signed - sum(shares, Decimal(0))
    return shares


def _rate_for_line(calculation: CalculationInput, line: DocumentLine) -> Decimal:
    if not calculation.treatment_of(line).charges_vat or line.tax_category in {
        TaxCategory.ZERO,
        TaxCategory.EXEMPT,
    }:
        return Decimal(0)
    return calculation.rate_for(line)


def calculate(calculation: CalculationInput) -> Totals:
    currency = calculation.currency
    step = currency.minor_step
    line_amounts = tuple(
        LineAmount(
            line_id=line.id,
            amount=Money(round_half_up(line.raw_amount(), step), currency),
            vat_code=vat_code(calculation.treatment_of(line), line.tax_category),
            tax_rate=_rate_for_line(calculation, line),
        )
        for line in calculation.lines
        if line.is_item
    )
    keys: list[tuple[VatCode, Decimal]] = []
    sums: dict[tuple[VatCode, Decimal], Decimal] = {}
    for line in line_amounts:
        key = _group_key(line)
        if key not in sums:
            keys.append(key)
            sums[key] = Decimal(0)
        sums[key] += line.amount.amount
    subtotal = sum(sums.values(), Decimal(0))
    discounts = (
        _allocate_discount([sums[key] for key in keys], calculation, subtotal) if keys else []
    )

    groups: list[TaxGroup] = []
    for key, group_discount in zip(keys, discounts, strict=True):
        code, rate = key
        after_discount = sums[key] - group_discount
        if calculation.price_mode is PriceMode.NET:
            net = after_discount
            tax = round_half_up(net * rate / HUNDRED, step)
        else:
            tax = round_half_up(after_discount * rate / (HUNDRED + rate), step)
            net = after_discount - tax
        groups.append(
            TaxGroup(
                vat_code=code,
                rate=rate,
                amount=Money(sums[key], currency),
                discount=Money(group_discount, currency),
                net=Money(net, currency),
                tax=Money(tax, currency),
            ),
        )

    net_total = sum((group.net.amount for group in groups), Decimal(0))
    tax_total = sum((group.tax.amount for group in groups), Decimal(0))
    gross = net_total + tax_total
    rounding_step = (
        CASH_ROUNDING_STEP if calculation.cash_rounding and currency.value == "CHF" else step
    )
    total = round_half_up(gross, rounding_step)
    return Totals(
        currency=currency,
        lines=line_amounts,
        groups=tuple(groups),
        subtotal=Money(subtotal, currency),
        discount=Money(sum(discounts, Decimal(0)), currency),
        net=Money(net_total, currency),
        tax=Money(tax_total, currency),
        gross=Money(gross, currency),
        rounding=Money(total - gross, currency),
        total=Money(total, currency),
    )
