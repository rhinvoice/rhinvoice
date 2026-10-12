from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rhinvoice.domain.catalog.unit import Unit
from rhinvoice.domain.document.calculation import CalculationInput, Totals, calculate
from rhinvoice.domain.document.lines import (
    Discount,
    DiscountKind,
    DocumentLine,
    LineKind,
    PriceMode,
)
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Currency, Money
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply
from rhinvoice.domain.tax.treatment import TaxTreatment
from rhinvoice.domain.tax.vat_code import VatCode

SWISS_RATES = {
    TaxCategory.STANDARD: Decimal("8.1"),
    TaxCategory.REDUCED: Decimal("2.6"),
    TaxCategory.SPECIAL: Decimal("3.8"),
}


def item(
    quantity: str,
    price: str,
    category: TaxCategory = TaxCategory.STANDARD,
    discount: str = "0",
    supply: Supply = Supply.SERVICE,
) -> DocumentLine:
    return DocumentLine(
        id=new_id(),
        kind=LineKind.ITEM,
        description="Position",
        quantity=Decimal(quantity),
        unit=Unit("C62"),
        unit_price=Decimal(price),
        discount_percent=Decimal(discount),
        tax_category=category,
        supply=supply,
    )


def compute(
    lines: list[DocumentLine],
    *,
    currency: Currency = Currency.CHF,
    mode: PriceMode = PriceMode.NET,
    discount: Discount | None = None,
    treatment: TaxTreatment = TaxTreatment.DOMESTIC,
    goods_treatment: TaxTreatment | None = None,
    cash_rounding: bool = True,
) -> Totals:
    return calculate(
        CalculationInput(
            currency=currency,
            price_mode=mode,
            lines=lines,
            discount=discount or Discount.none(),
            treatment=treatment,
            rate_for=lambda line: SWISS_RATES[line.tax_category],
            cash_rounding=cash_rounding,
            goods_treatment=goods_treatment,
        ),
    )


def chf(value: str) -> Money:
    return Money(Decimal(value), Currency.CHF)


def test_swiss_invoice_with_two_rates_and_cash_rounding() -> None:
    lines = [item("10", "150"), item("3", "12.35", TaxCategory.REDUCED)]
    totals = compute(lines)
    assert totals.currency is Currency.CHF
    assert [amount.line_id for amount in totals.lines] == [line.id for line in lines]
    assert totals.subtotal == chf("1537.05")
    assert [(g.rate, g.net, g.tax) for g in totals.groups] == [
        (Decimal("8.1"), chf("1500"), chf("121.50")),
        (Decimal("2.6"), chf("37.05"), chf("0.96")),
    ]
    assert totals.net == chf("1537.05")
    assert totals.tax == chf("122.46")
    assert totals.gross == chf("1659.51")
    assert totals.rounding == chf("-0.01")
    assert totals.total == chf("1659.50")
    assert totals.groups[0].gross == chf("1621.50")


def test_line_discount_and_line_rounding() -> None:
    totals = compute([item("1", "99.99", discount="10")], cash_rounding=False)
    assert totals.lines[0].amount == chf("89.99")
    assert totals.tax == chf("7.29")
    assert totals.total == chf("97.28")
    assert totals.rounding == chf("0")


def test_percent_document_discount_per_group() -> None:
    totals = compute(
        [item("1", "100"), item("1", "50", TaxCategory.REDUCED)],
        discount=Discount(DiscountKind.PERCENT, Decimal(10)),
        cash_rounding=False,
    )
    assert [g.discount for g in totals.groups] == [chf("10.00"), chf("5.00")]
    assert totals.discount == chf("15.00")
    assert totals.net == chf("135.00")
    assert totals.tax == chf("8.46")  # 90 x 8.1 % = 7.29, 45 x 2.6 % = 1.17
    assert totals.total == chf("143.46")


def test_amount_discount_is_distributed_proportionally() -> None:
    totals = compute(
        [item("1", "200"), item("1", "100", TaxCategory.REDUCED)],
        discount=Discount(DiscountKind.AMOUNT, Decimal(10)),
        cash_rounding=False,
    )
    assert [g.discount for g in totals.groups] == [chf("6.67"), chf("3.33")]
    assert totals.discount == chf("10")
    assert totals.net == chf("290")


def test_amount_discount_remainder_goes_to_the_largest_group() -> None:
    # 0.02 x 100/500 = 0.004 -> 0.00, 0.02 x 300/500 = 0.012 -> 0.01; the missing cent
    # goes to the largest group, even though it is not the last one.
    totals = compute(
        [
            item("1", "100"),
            item("1", "300", TaxCategory.REDUCED),
            item("1", "100", TaxCategory.SPECIAL),
        ],
        discount=Discount(DiscountKind.AMOUNT, Decimal("0.02")),
        cash_rounding=False,
    )
    assert [g.discount for g in totals.groups] == [chf("0"), chf("0.02"), chf("0")]


def test_amount_discount_on_groups_that_cancel_out() -> None:
    totals = compute(
        [item("1", "100"), item("-1", "100", TaxCategory.REDUCED)],
        discount=Discount(DiscountKind.AMOUNT, Decimal(0)),
    )
    assert totals.subtotal == chf("0")
    assert [g.discount for g in totals.groups] == [chf("0"), chf("0")]
    assert [g.net for g in totals.groups] == [chf("100"), chf("-100")]


def test_amount_discount_larger_than_amount_is_rejected() -> None:
    with pytest.raises(ValidationError) as error:
        compute([item("1", "5")], discount=Discount(DiscountKind.AMOUNT, Decimal("5.01")))
    assert error.value.details == {"discount": "the discount is larger than the document amount"}
    assert compute(
        [item("1", "5")], discount=Discount(DiscountKind.AMOUNT, Decimal(5))
    ).total == chf("0")


def test_gross_prices_extract_the_tax() -> None:
    totals = compute([item("1", "108.10")], mode=PriceMode.GROSS, cash_rounding=False)
    assert totals.groups[0].tax == chf("8.10")
    assert totals.net == chf("100.00")
    assert totals.total == chf("108.10")


@pytest.mark.parametrize(
    ("treatment", "code"),
    [
        (TaxTreatment.EXPORT, VatCode.EXPORT),
        (TaxTreatment.REVERSE_CHARGE, VatCode.REVERSE_CHARGE),
        (TaxTreatment.SMALL_BUSINESS, VatCode.EXEMPT),
        (TaxTreatment.EXEMPT, VatCode.EXEMPT),
    ],
)
def test_treatments_without_vat(treatment: TaxTreatment, code: VatCode) -> None:
    totals = compute([item("2", "50"), item("1", "10", TaxCategory.REDUCED)], treatment=treatment)
    assert totals.tax == chf("0")
    assert [(g.vat_code, g.rate) for g in totals.groups] == [(code, Decimal(0))]
    assert totals.total == chf("110")


def test_goods_and_services_are_grouped_by_their_own_treatment() -> None:
    # An Austrian company invoices a private customer in Switzerland: the service is
    # taxed at home, the goods are an export delivery.
    service = item("1", "100")
    goods = item("2", "50", supply=Supply.GOODS)
    totals = compute(
        [service, goods, item("1", "10", TaxCategory.REDUCED, supply=Supply.GOODS)],
        goods_treatment=TaxTreatment.GOODS_EXPORT,
    )
    assert [(g.vat_code, g.rate, g.net, g.tax) for g in totals.groups] == [
        (VatCode.STANDARD, Decimal("8.1"), chf("100"), chf("8.10")),
        (VatCode.EXPORT, Decimal(0), chf("110"), chf("0")),
    ]
    assert [(line.vat_code, line.tax_rate) for line in totals.lines][:2] == [
        (VatCode.STANDARD, Decimal("8.1")),
        (VatCode.EXPORT, Decimal(0)),
    ]
    assert totals.total == chf("218.10")


def test_goods_follow_the_document_without_a_treatment_of_their_own() -> None:
    goods = item("1", "100", supply=Supply.GOODS)
    assert compute([goods]).tax == chf("8.10")
    reverse_charge = compute(
        [item("1", "10"), goods],
        treatment=TaxTreatment.REVERSE_CHARGE,
        goods_treatment=TaxTreatment.INTRA_COMMUNITY,
    )
    assert [g.vat_code for g in reverse_charge.groups] == [
        VatCode.REVERSE_CHARGE,
        VatCode.INTRA_COMMUNITY,
    ]


def test_zero_and_exempt_categories_have_no_tax() -> None:
    totals = compute([item("1", "10", TaxCategory.ZERO), item("1", "10", TaxCategory.EXEMPT)])
    assert [(g.vat_code, g.tax) for g in totals.groups] == [
        (VatCode.ZERO, chf("0")),
        (VatCode.EXEMPT, chf("0")),
    ]


def test_text_lines_and_empty_documents() -> None:
    text = DocumentLine(id=new_id(), kind=LineKind.TEXT, description="Phase 1")
    totals = compute([text])
    assert totals.lines == ()
    assert totals.groups == ()
    assert totals.total == chf("0")
    amount_discount = compute([text], discount=Discount(DiscountKind.AMOUNT, Decimal(0)))
    assert amount_discount.discount == chf("0")


def test_euro_has_no_cash_rounding() -> None:
    totals = compute([item("1", "10.01")], currency=Currency.EUR)
    assert totals.total.amount == Decimal("10.82")
    assert totals.rounding.amount == 0


def test_document_line_validation() -> None:
    with pytest.raises(ValidationError) as missing:
        DocumentLine(id=new_id(), kind=LineKind.ITEM, description=" ")
    assert missing.value.details == {"description": "description is required"}
    with pytest.raises(ValidationError) as empty_text:
        DocumentLine(id=new_id(), kind=LineKind.TEXT, description="")
    assert empty_text.value.details == {"description": "a text line needs a text"}
    assert (
        DocumentLine(id=new_id(), kind=LineKind.TEXT, description="", details="Hinweis").details
        == "Hinweis"
    )
    with pytest.raises(ValidationError) as long_details:
        DocumentLine(id=new_id(), kind=LineKind.TEXT, description="x", details="x" * 4001)
    assert long_details.value.details == {"details": "details must be at most 4000 characters long"}
    highest = DocumentLine(
        id=new_id(), kind=LineKind.ITEM, description="x", unit_price=Decimal("99999999.9999")
    )
    assert highest.unit_price == Decimal("99999999.9999")
    cases = [
        ({"quantity": Decimal(1000000000)}, "quantity", "quantity is too large"),
        ({"quantity": Decimal("1.00001")}, "quantity", "quantity has too many decimal places"),
        (
            {"unit_price": Decimal(-1)},
            "unit_price",
            "unit price must be between 0 and 99999999.9999",
        ),
        (
            {"unit_price": Decimal(100000000)},
            "unit_price",
            "unit price must be between 0 and 99999999.9999",
        ),
        (
            {"unit_price": Decimal("1.00001")},
            "unit_price",
            "unit price has too many decimal places",
        ),
        (
            {"discount_percent": Decimal(-1)},
            "discount_percent",
            "discount must be between 0 and 100 percent",
        ),
        (
            {"discount_percent": Decimal(101)},
            "discount_percent",
            "discount must be between 0 and 100 percent",
        ),
        (
            {"discount_percent": Decimal("1.001")},
            "discount_percent",
            "discount has too many decimal places",
        ),
    ]
    for overrides, field, message in cases:
        with pytest.raises(ValidationError) as error:
            DocumentLine(id=new_id(), kind=LineKind.ITEM, description="x", **overrides)  # type: ignore[arg-type]  # dynamic test values
        assert error.value.details == {field: message}
    assert (
        DocumentLine(
            id=new_id(), kind=LineKind.ITEM, description="x", quantity=Decimal(-999999999)
        ).quantity
        < 0
    )


def test_discount_validation() -> None:
    assert Discount.none() == Discount(DiscountKind.PERCENT, Decimal(0))
    assert Discount.none().is_zero
    assert not Discount(DiscountKind.AMOUNT, Decimal(1)).is_zero
    assert Discount(DiscountKind.PERCENT, Decimal(100)).value == 100
    for kind, value, message in [
        (DiscountKind.PERCENT, "-1", "discount must not be negative"),
        (DiscountKind.PERCENT, "100.01", "discount must be between 0 and 100 percent"),
        (DiscountKind.PERCENT, "1.001", "discount has too many decimal places"),
        (DiscountKind.AMOUNT, "1.001", "discount has too many decimal places"),
    ]:
        with pytest.raises(ValidationError) as error:
            Discount(kind, Decimal(value))
        assert error.value.details == {"discount": message}


# --- Properties -------------------------------------------------------------------

quantities = st.decimals(min_value=Decimal("0.0001"), max_value=Decimal(10000), places=4)
prices = st.decimals(min_value=Decimal(0), max_value=Decimal(100000), places=4)
percents = st.decimals(min_value=Decimal(0), max_value=Decimal(100), places=2)
categories = st.sampled_from(
    [TaxCategory.STANDARD, TaxCategory.REDUCED, TaxCategory.SPECIAL, TaxCategory.ZERO]
)


def _item_from(
    quantity: Decimal, price: Decimal, discount: Decimal, category: TaxCategory
) -> DocumentLine:
    return item(str(quantity), str(price), category, str(discount))


line_strategy = st.builds(_item_from, quantities, prices, percents, categories)
line_lists = st.lists(line_strategy, min_size=1, max_size=8)
modes = st.sampled_from(list(PriceMode))


@given(line_lists, percents, modes)
def test_totals_are_consistent(
    lines: list[DocumentLine], discount: Decimal, mode: PriceMode
) -> None:
    totals = compute(lines, discount=Discount(DiscountKind.PERCENT, discount), mode=mode)
    assert totals.subtotal == sum((line.amount for line in totals.lines), chf("0"))
    assert totals.net + totals.tax == totals.gross
    assert totals.gross + totals.rounding == totals.total
    assert sum((g.gross for g in totals.groups), chf("0")) == totals.gross
    assert sum((g.discount for g in totals.groups), chf("0")) == totals.discount
    for group in totals.groups:
        assert group.amount - group.discount == (
            group.net if mode is PriceMode.NET else group.gross
        )
    assert abs(totals.rounding.amount) <= Decimal("0.025")
    assert (totals.total.amount * 20) % 1 == 0


@given(line_lists, percents)
def test_group_tax_is_within_half_a_cent(lines: list[DocumentLine], discount: Decimal) -> None:
    totals = compute(lines, discount=Discount(DiscountKind.PERCENT, discount))
    for group in totals.groups:
        exact = group.net.amount * group.rate / 100
        assert abs(group.tax.amount - exact) <= Decimal("0.005")


@given(line_lists, st.randoms(use_true_random=False))
def test_line_order_does_not_change_the_totals(lines: list[DocumentLine], random: object) -> None:
    shuffled = list(lines)
    random.shuffle(shuffled)  # type: ignore[attr-defined]  # hypothesis Random
    first, second = compute(lines), compute(shuffled)
    assert (first.net, first.tax, first.total) == (second.net, second.tax, second.total)


@given(line_lists, st.decimals(min_value=Decimal(0), max_value=Decimal(50), places=2), modes)
def test_cancellation_negates_every_amount(
    lines: list[DocumentLine], amount: Decimal, mode: PriceMode
) -> None:
    """A cancellation negates the quantities; all amounts must be exactly negated."""
    negated = [
        DocumentLine(
            id=line.id,
            kind=line.kind,
            description=line.description,
            quantity=-line.quantity,
            unit=line.unit,
            unit_price=line.unit_price,
            discount_percent=line.discount_percent,
            tax_category=line.tax_category,
        )
        for line in lines
    ]
    original = compute(lines, mode=mode)
    subtotal = original.subtotal.amount
    discount = Discount(DiscountKind.AMOUNT, min(amount, subtotal))
    original = compute(lines, discount=discount, mode=mode)
    cancelled = compute(negated, discount=discount, mode=mode)
    assert cancelled.total == -original.total
    assert cancelled.tax == -original.tax
    assert [(g.net, g.tax, g.discount) for g in cancelled.groups] == [
        (-g.net, -g.tax, -g.discount) for g in original.groups
    ]
