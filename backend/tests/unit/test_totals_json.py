from decimal import Decimal

from rhinvoice.domain.document.calculation import CalculationInput, calculate
from rhinvoice.domain.document.lines import Discount, DocumentLine, LineKind, PriceMode
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Currency, Money
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.treatment import TaxTreatment
from rhinvoice.infrastructure.db.serialization import totals_from_json, totals_to_json


def line(category: TaxCategory) -> DocumentLine:
    return DocumentLine(
        id=new_id(),
        kind=LineKind.ITEM,
        description="Position",
        unit_price=Decimal("100.00"),
        tax_category=category,
        tax_rate_id=None if category is TaxCategory.PASS_THROUGH else new_id(),
    )


def test_totals_with_pass_through_lines_survive_the_round_trip() -> None:
    totals = calculate(
        CalculationInput(
            currency=Currency.EUR,
            price_mode=PriceMode.NET,
            lines=[line(TaxCategory.STANDARD), line(TaxCategory.PASS_THROUGH)],
            discount=Discount.none(),
            treatment=TaxTreatment.DOMESTIC,
            rate_for=lambda _: Decimal(19),
            cash_rounding=False,
        )
    )
    stored = totals_to_json(totals)
    assert stored["pass_through"] == "100.00"
    assert [item["pass_through"] for item in stored["lines"]] == [False, True]
    assert totals_from_json(stored) == totals


def test_totals_frozen_before_pass_through_lines_have_none() -> None:
    totals = calculate(
        CalculationInput(
            currency=Currency.CHF,
            price_mode=PriceMode.NET,
            lines=[line(TaxCategory.STANDARD)],
            discount=Discount.none(),
            treatment=TaxTreatment.DOMESTIC,
            rate_for=lambda _: Decimal("8.1"),
            cash_rounding=True,
        )
    )
    stored = totals_to_json(totals)
    del stored["pass_through"]
    for item in stored["lines"]:
        del item["pass_through"]
    old = totals_from_json(stored)
    assert old.pass_through == Money(Decimal("0.00"), Currency.CHF)
    assert str(old.pass_through.amount) == "0.00"
    assert old.lines == totals.lines
