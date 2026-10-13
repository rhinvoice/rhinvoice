"""Writing off invoices that will not be paid: status, amounts, later payments and the way back."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from rhinvoice.domain.document.document import (
    DisplayStatus,
    Document,
    DocumentEvent,
    DocumentStatus,
    DocumentType,
    EventKind,
    Payment,
)
from rhinvoice.domain.document.write_off import WriteOff, WriteOffReason, tax_share
from rhinvoice.domain.shared.errors import (
    CurrencyMismatchError,
    InvalidStateError,
    ValidationError,
)
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Currency, Money
from tests.helpers import raises_exactly
from tests.unit.domain.test_document import NOW, TODAY, draft, issued, pay
from tests.unit.domain.test_imported_document import imported

LATER = NOW + timedelta(hours=1)
MUCH_LATER = NOW + timedelta(days=400)


def chf(value: str) -> Money:
    return Money(Decimal(value), Currency.CHF)


def written_off(
    document: Document,
    on: date = TODAY,
    reason: WriteOffReason = WriteOffReason.GONE,
    note: str = "",
) -> Document:
    return document.record_write_off(new_id(), on, reason, LATER, note=note)


def recover(document: Document, amount: str, paid_on: date = TODAY) -> Document:
    payment = Payment(id=new_id(), paid_on=paid_on, amount=chf(amount), recorded_at=MUCH_LATER)
    return document.add_payment(payment, MUCH_LATER)


def test_writing_off_closes_the_open_amount() -> None:
    invoice = issued()
    lost = written_off(invoice, note=" Konkurs eröffnet ")
    assert lost.status is DocumentStatus.WRITTEN_OFF
    assert lost.open_amount() == Money.zero(Currency.CHF)
    assert lost.written_off_amount == chf("1659.50")
    assert lost.paid_amount == Money.zero(Currency.CHF)
    assert lost.write_off is not None
    assert lost.write_off.amount == chf("1659.50")
    assert lost.write_off.written_off_on == TODAY
    assert lost.write_off.reason is WriteOffReason.GONE
    assert lost.write_off.note == "Konkurs eröffnet"
    assert lost.write_off.recorded_at == LATER
    assert lost.events[-1] == DocumentEvent(
        LATER, EventKind.WRITTEN_OFF, f"1659.50 {TODAY.isoformat()} gone"
    )
    # The invoice itself is untouched.
    assert lost.content == invoice.content
    assert lost.issued_totals == invoice.issued_totals
    assert lost.number == invoice.number
    assert invoice.written_off_amount == Money.zero(Currency.CHF)
    assert invoice.recovered_amount == Money.zero(Currency.CHF)


def test_only_the_rest_after_part_payments_is_written_off() -> None:
    lost = written_off(pay(issued(), "1000"))
    assert lost.status is DocumentStatus.WRITTEN_OFF
    assert lost.write_off is not None
    assert lost.write_off.amount == chf("659.50")
    assert lost.written_off_amount == chf("659.50")
    assert lost.paid_amount == chf("1000")
    assert lost.open_amount() == Money.zero(Currency.CHF)


def test_a_written_off_invoice_is_never_overdue() -> None:
    lost = written_off(issued())
    assert lost.display_status(TODAY + timedelta(days=999)) is DisplayStatus.WRITTEN_OFF


def test_the_date_may_lie_back_to_the_invoice_date() -> None:
    invoice = issued()
    assert written_off(invoice, on=TODAY).write_off is not None
    old = imported(open_amount="1296.00")
    lost = written_off(old, on=date(2015, 12, 31))
    assert lost.write_off is not None
    assert lost.write_off.written_off_on == date(2015, 12, 31)
    assert written_off(old, on=date(2015, 2, 14)).status is DocumentStatus.WRITTEN_OFF
    with raises_exactly(ValidationError, "an invoice is not written off before its date") as early:
        written_off(old, on=date(2015, 2, 13))
    assert early.value.field == "written_off_on"
    assert early.value.code == "write_off_before_invoice"


def test_what_cannot_be_written_off() -> None:
    with raises_exactly(InvalidStateError, "a draft invoice cannot be written off"):
        written_off(draft())
    paid = pay(issued(), "1659.50")
    with raises_exactly(InvalidStateError, "a paid invoice cannot be written off"):
        written_off(paid)
    lost = written_off(issued())
    with raises_exactly(InvalidStateError, "a written_off invoice cannot be written off"):
        written_off(lost)
    with raises_exactly(InvalidStateError, "a sent quote cannot be written off"):
        written_off(issued(DocumentType.QUOTE))
    cancellation = replace(issued(), type=DocumentType.CANCELLATION)
    with raises_exactly(InvalidStateError, "only invoices are written off"):
        written_off(cancellation)


def test_written_off_invoices_are_not_reminded_or_cancelled() -> None:
    lost = written_off(issued())
    with raises_exactly(InvalidStateError, "a written_off invoice cannot be reminded"):
        lost.record_reminder(1, NOW)
    with raises_exactly(InvalidStateError, "a written_off invoice cannot be cancelled"):
        lost.cancel_check()
    with raises_exactly(InvalidStateError, "a written_off invoice cannot be paid"):
        lost.pay_in_full(new_id(), TODAY, MUCH_LATER)


def test_removing_a_write_off_reopens_the_invoice() -> None:
    lost = written_off(issued())
    reopened = lost.remove_write_off(MUCH_LATER)
    assert reopened.status is DocumentStatus.ISSUED
    assert reopened.write_off is None
    assert reopened.open_amount() == chf("1659.50")
    assert reopened.written_off_amount == Money.zero(Currency.CHF)
    assert reopened.events[-1] == DocumentEvent(MUCH_LATER, EventKind.WRITE_OFF_REMOVED, "1659.50")
    partly = written_off(pay(issued(), "1000")).remove_write_off(MUCH_LATER)
    assert partly.status is DocumentStatus.PARTIALLY_PAID
    assert partly.open_amount() == chf("659.50")
    with raises_exactly(InvalidStateError, "a issued invoice cannot be reopened"):
        issued().remove_write_off(NOW)


def test_a_later_payment_is_a_recovery_and_the_write_off_stays() -> None:
    lost = written_off(pay(issued(), "1000"))
    partly = recover(lost, "100")
    assert partly.status is DocumentStatus.WRITTEN_OFF
    assert partly.open_amount() == Money.zero(Currency.CHF)
    assert partly.written_off_amount == chf("559.50")
    assert partly.recovered_amount == chf("100")
    assert partly.write_off is not None
    assert partly.write_off.amount == chf("659.50")
    assert partly.recoveries == (partly.payments[1],)
    assert partly.events[-1].kind is EventKind.PAYMENT_ADDED

    whole = recover(partly, "559.50")
    assert whole.status is DocumentStatus.PAID
    assert whole.written_off_amount == Money.zero(Currency.CHF)
    assert whole.recovered_amount == chf("659.50")
    assert whole.write_off is not None
    assert whole.display_status(TODAY + timedelta(days=999)) is DisplayStatus.PAID
    with raises_exactly(InvalidStateError, "a paid invoice cannot be reopened"):
        whole.remove_write_off(MUCH_LATER)

    # Removing a recovery leads back to the written-off invoice, never to an open one.
    back = whole.remove_payment(whole.payments[2].id, MUCH_LATER)
    assert back.status is DocumentStatus.WRITTEN_OFF
    assert back.written_off_amount == chf("559.50")
    none = back.remove_payment(back.payments[1].id, MUCH_LATER)
    assert none.status is DocumentStatus.WRITTEN_OFF
    assert none.recovered_amount == Money.zero(Currency.CHF)
    assert none.recoveries == ()


def test_a_recovery_does_not_exceed_what_was_written_off() -> None:
    lost = written_off(pay(issued(), "1000"))
    with raises_exactly(
        ValidationError, "the payment exceeds the open amount of CHF 659.50"
    ) as exceeded:
        recover(lost, "659.55")
    assert exceeded.value.code == "payment_exceeds_open_amount"


def test_recoveries_are_recorded_after_the_write_off() -> None:
    lost = written_off(issued())
    same_moment = Payment(id=new_id(), paid_on=TODAY, amount=chf("1"), recorded_at=LATER)
    with raises_exactly(
        InvalidStateError, "a payment of a written-off invoice is recorded after the write-off"
    ):
        lost.add_payment(same_moment, LATER)


def test_payments_from_before_the_write_off_stay() -> None:
    lost = recover(written_off(pay(issued(), "1000")), "100")
    with raises_exactly(
        InvalidStateError, "remove the write-off before a payment made before it"
    ) as refused:
        lost.remove_payment(lost.payments[0].id, MUCH_LATER)
    assert refused.value.code == "payment_before_write_off"


def test_imported_invoices_are_written_off_like_any_other() -> None:
    lost = written_off(imported(open_amount="296.00"), on=date(2016, 1, 1))
    assert lost.status is DocumentStatus.WRITTEN_OFF
    assert lost.written_off_amount == chf("296.00")
    assert lost.paid_amount == chf("1000.00")


def test_write_off_validation() -> None:
    for amount, message in [
        ("0", "a write-off must be a positive amount"),
        ("-1", "a write-off must be a positive amount"),
        ("1.001", "a write-off has at most two decimal places"),
    ]:
        with raises_exactly(ValidationError, message) as error:
            WriteOff(
                id=new_id(),
                written_off_on=TODAY,
                amount=chf(amount),
                reason=WriteOffReason.OTHER,
                recorded_at=NOW,
            )
        assert error.value.field == "amount"
    with raises_exactly(ValidationError, "note must be at most 500 characters long") as long:
        written_off(issued(), note="x" * 501)
    assert long.value.field == "note"


# --- The tax contained in a written-off amount ------------------------------------------


def test_the_tax_share_of_the_whole_invoice_is_its_tax() -> None:
    invoice = issued()
    totals = invoice.frozen_totals
    assert not totals.tax.is_zero
    assert tax_share(totals.total, totals) == totals.tax


def test_the_tax_share_of_a_rest_is_proportional() -> None:
    old = imported(total="1296.00", net="1200.00", open_amount="648.00")
    assert tax_share(chf("648.00"), old.frozen_totals) == chf("48.00")
    # Half a centime is rounded up, as everywhere.
    assert tax_share(chf("0.10"), old.frozen_totals) == chf("0.01")
    assert tax_share(chf("0.06"), old.frozen_totals) == chf("0.00")


def test_invoices_without_tax_have_no_tax_share() -> None:
    old = imported(total="20.00", net="20.00", open_amount="20.00")
    assert tax_share(chf("20.00"), old.frozen_totals) == Money.zero(Currency.CHF)


def test_the_tax_share_is_in_the_currency_of_the_invoice() -> None:
    old = imported(total="20.00", net="20.00", open_amount="20.00")
    with raises_exactly(CurrencyMismatchError, "the amount must be in CHF"):
        tax_share(Money(Decimal(1), Currency.EUR), old.frozen_totals)


@given(
    net=st.integers(min_value=1, max_value=10_000_000),
    rate=st.sampled_from(["0", "2.6", "3.8", "7", "8.1", "10", "13", "19", "20"]),
    part=st.integers(min_value=1, max_value=10_000_000),
)
def test_tax_share_properties(net: int, rate: str, part: int) -> None:
    net_amount = Money.from_minor(net, Currency.CHF)
    tax = net_amount.percent(Decimal(rate)).round_to_minor()
    total = net_amount + tax
    old = imported(
        total=str(total.amount), net=str(net_amount.amount), open_amount=str(total.amount)
    )
    amount = Money.from_minor(min(part, total.to_minor()), Currency.CHF)
    share = tax_share(amount, old.frozen_totals)
    assert Money.zero(Currency.CHF) <= share <= tax
    assert share <= amount
    assert share == share.round_to_minor()
    assert tax_share(total, old.frozen_totals) == tax
