"""Invoices of a program used before: their amounts, payments, files and what they refuse."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from rhinvoice.domain.document.attachment import Attachment
from rhinvoice.domain.document.document import (
    Document,
    DocumentOrigin,
    DocumentStatus,
    DocumentType,
    EventKind,
)
from rhinvoice.domain.shared.country import Country
from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Currency, Money
from tests.helpers import raises_exactly
from tests.unit.domain.test_document import NOW, content, issued, snapshot

ISSUED_ON = date(2015, 2, 14)
DUE_ON = date(2015, 2, 28)
SHA = "a" * 64


def chf(value: str) -> Money:
    return Money(Decimal(value), Currency.CHF)


def imported(
    total: str = "1296.00", net: str = "1200.00", open_amount: str = "0", **overrides: object
) -> Document:
    values: dict[str, object] = {"issue_date": ISSUED_ON, "due_date": DUE_ON, "lines": ()}
    values.update(overrides)
    return Document.imported(
        new_id(),
        number=" R20150001 ",
        content=content(**values),
        snapshot=snapshot(),
        net=chf(net),
        total=chf(total),
        open_amount=chf(open_amount),
        now=NOW,
        source="2015/Rechnung R20150001.pdf",
    )


def test_an_imported_invoice_keeps_the_amounts_of_the_program() -> None:
    document = imported()
    assert document.type is DocumentType.INVOICE
    assert document.origin is DocumentOrigin.IMPORTED
    assert document.is_imported
    assert document.number == "R20150001"
    assert document.content.lines == ()
    assert document.content.due_date == DUE_ON
    assert (document.created_at, document.issued_at) == (NOW, NOW)
    assert document.snapshot is not None
    totals = document.issued_totals
    assert totals is not None
    assert (totals.net, totals.tax, totals.gross, totals.total) == (
        chf("1200.00"),
        chf("96.00"),
        chf("1296.00"),
        chf("1296.00"),
    )
    assert (totals.subtotal, totals.discount, totals.rounding) == (
        chf("1200.00"),
        chf("0"),
        chf("0"),
    )
    assert (totals.lines, totals.groups) == ((), ())
    assert document.totals(Country.CH, cash_rounding=True, today=ISSUED_ON) is totals
    assert [(event.kind, event.detail) for event in document.events] == [
        (EventKind.IMPORTED, "2015/Rechnung R20150001.pdf")
    ]


def test_what_was_paid_becomes_one_payment_on_the_due_date() -> None:
    paid = imported()
    assert paid.status is DocumentStatus.PAID
    [payment] = paid.payments
    assert (payment.paid_on, payment.amount, payment.recorded_at) == (DUE_ON, chf("1296.00"), NOW)
    assert paid.open_amount() == chf("0")

    partly = imported(open_amount="296.00")
    assert partly.status is DocumentStatus.PARTIALLY_PAID
    assert partly.paid_amount == chf("1000.00")
    assert partly.open_amount() == chf("296.00")

    unpaid = imported(open_amount="1296.00")
    assert unpaid.status is DocumentStatus.ISSUED
    assert unpaid.payments == ()
    # Open imported invoices take payments like any other.
    later = unpaid.pay_in_full(new_id(), date(2026, 3, 9), NOW)
    assert later.status is DocumentStatus.PAID


def test_without_a_due_date_the_invoice_is_due_on_its_date() -> None:
    document = imported(due_date=None)
    assert document.content.due_date == ISSUED_ON
    assert document.payments[0].paid_on == ISSUED_ON


def test_a_long_source_is_shortened_in_the_history() -> None:
    document = Document.imported(
        new_id(),
        number="R1",
        content=content(issue_date=ISSUED_ON, lines=()),
        snapshot=snapshot(),
        net=chf("10"),
        total=chf("10"),
        open_amount=chf("0"),
        now=NOW,
        source="x" * 600,
    )
    assert len(document.events[0].detail) == 500
    assert document.events[0].detail == "x" * 500


@pytest.mark.parametrize(
    ("overrides", "field", "message", "code"),
    [
        ({"issue_date": None}, "issue_date", "issue_date is required", "validation_error"),
        (
            {"total": "0"},
            "total",
            "the total of an invoice must be positive",
            "non_positive_total",
        ),
        (
            {"total": "-10", "net": "-10"},
            "total",
            "the total of an invoice must be positive",
            "non_positive_total",
        ),
        (
            {"net": "1300"},
            "net",
            "the net amount lies between zero and the total",
            "net_above_total",
        ),
        (
            {"net": "-1"},
            "net",
            "the net amount lies between zero and the total",
            "net_above_total",
        ),
        (
            {"open_amount": "1296.05"},
            "open_amount",
            "the open amount lies between zero and the total",
            "open_above_total",
        ),
        (
            {"open_amount": "-0.05"},
            "open_amount",
            "the open amount lies between zero and the total",
            "open_above_total",
        ),
        (
            {"net": "1200.001"},
            "net",
            "an amount has at most two decimal places",
            "validation_error",
        ),
        (
            {"total": "1296.001"},
            "total",
            "an amount has at most two decimal places",
            "validation_error",
        ),
        (
            {"open_amount": "0.001"},
            "open_amount",
            "an amount has at most two decimal places",
            "validation_error",
        ),
    ],
)
def test_amounts_and_dates_are_checked(
    overrides: dict[str, object], field: str, message: str, code: str
) -> None:
    # The parameters are shared between runs: read them, never change them.
    names = ("total", "net", "open_amount")
    amounts = {key: str(value) for key, value in overrides.items() if key in names}
    others = {key: value for key, value in overrides.items() if key not in names}
    with raises_exactly(ValidationError, message) as caught:
        imported(**amounts, **others)  # type: ignore[arg-type]  # test builder
    assert (caught.value.field, caught.value.code) == (field, code)


def test_the_amounts_are_in_the_currency_of_the_invoice() -> None:
    with raises_exactly(ValidationError, "the amounts must be in CHF") as caught:
        Document.imported(
            new_id(),
            number="R1",
            content=content(issue_date=ISSUED_ON, lines=()),
            snapshot=snapshot(),
            net=chf("10"),
            total=Money(Decimal(10), Currency.EUR),
            open_amount=chf("0"),
            now=NOW,
        )
    assert caught.value.field == "currency"


@pytest.mark.parametrize("number", ["", "   ", "R" * 31, "R1\n2"])
def test_the_number_is_checked(number: str) -> None:
    with pytest.raises(ValidationError) as caught:
        Document.imported(
            new_id(),
            number=number,
            content=content(issue_date=ISSUED_ON, lines=()),
            snapshot=snapshot(),
            net=chf("10"),
            total=chf("10"),
            open_amount=chf("0"),
            now=NOW,
        )
    assert caught.value.field == "number"


def test_imported_invoices_consist_of_their_pdf() -> None:
    document = imported()
    for action in (
        lambda: document.copy_as_draft(new_id(), DocumentType.INVOICE, NOW),
        document.cancel_check,
        lambda: document.cancellation_draft(new_id(), NOW),
    ):
        with pytest.raises(InvalidStateError) as caught:
            action()
        assert caught.value.code == "imported_document"
    with raises_exactly(InvalidStateError, "an imported invoice cannot be copied"):
        document.copy_as_draft(new_id(), DocumentType.QUOTE, NOW)
    with raises_exactly(InvalidStateError, "an imported invoice cannot be cancelled"):
        document.cancel_check()
    # Its PDF is archived like any other: once.
    archived = document.archive_pdf(SHA)
    assert archived.pdf_sha256 == SHA


def test_files_are_recorded_on_imported_invoices_only() -> None:
    document = imported().record_file("Mahnung R20150001.pdf", NOW)
    assert (document.events[-1].kind, document.events[-1].detail) == (
        EventKind.FILE_ADDED,
        "Mahnung R20150001.pdf",
    )
    assert len(imported().record_file("y" * 600, NOW).events[-1].detail) == 500
    with raises_exactly(InvalidStateError, "files are added to imported invoices only") as caught:
        issued().record_file("x.pdf", NOW)
    assert caught.value.code == "not_imported"


def test_documents_written_here_are_no_imports() -> None:
    document = issued()
    assert document.origin is DocumentOrigin.RHINVOICE
    assert not document.is_imported
    assert not replace(document, origin=DocumentOrigin.RHINVOICE).is_imported


ADDED = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


def test_attachments_are_checked() -> None:
    attachment = Attachment(
        id=new_id(),
        document_id=new_id(),
        file_name="  2016/Rechnung R20160032_teil.pdf ",
        sha256=SHA,
        size=12,
        added_at=ADDED,
    )
    assert attachment.file_name == "2016/Rechnung R20160032_teil.pdf"
    for changes, field in (
        ({"file_name": " "}, "file_name"),
        ({"file_name": "x" * 256}, "file_name"),
        ({"sha256": "A" * 64}, "sha256"),
        ({"sha256": "a" * 63}, "sha256"),
        ({"size": 0}, "size"),
    ):
        with pytest.raises(ValidationError) as caught:
            replace(attachment, **changes)
        assert caught.value.field == field
    with raises_exactly(ValidationError, "an attachment is not empty"):
        replace(attachment, size=0)
    with raises_exactly(ValidationError, "a SHA-256 hash has 64 lowercase hex digits"):
        replace(attachment, sha256="x")


def test_lines_are_never_taken_over_and_the_history_has_the_time() -> None:
    document = imported(lines=content().lines)
    assert document.content.lines == ()
    assert document.events[0].at == NOW
    assert document.frozen_totals is document.issued_totals
    assert document.record_file("x.pdf", NOW).events[-1].at == NOW
    with raises_exactly(InvalidStateError, "the document has not been issued yet"):
        _ = issued().copy_as_draft(new_id(), DocumentType.INVOICE, NOW).frozen_totals


def test_small_amounts_count_too() -> None:
    # A net of zero (all of it tax) and cents paid are taken as the file says.
    document = imported(total="0.50", net="0", open_amount="0.10")
    assert document.status is DocumentStatus.PARTIALLY_PAID
    assert document.payments[0].amount == chf("0.40")
    assert document.payments[0].id != imported(total="0.50", net="0").payments[0].id
    totals = document.frozen_totals
    assert (totals.net, totals.tax, totals.total.currency) == (chf("0"), chf("0.50"), Currency.CHF)
    assert imported(total="0.01", net="0.01").status is DocumentStatus.PAID
    assert (
        Document.imported(
            new_id(),
            number="R1",
            content=content(issue_date=ISSUED_ON, lines=()),
            snapshot=snapshot(),
            net=chf("1"),
            total=chf("1"),
            open_amount=chf("0"),
            now=NOW,
        )
        .events[0]
        .detail
        == ""
    )


def test_a_payment_is_never_dated_after_the_import() -> None:
    # Imported on 9 March 2026; the invoice is due a month later and half paid.
    document = imported(
        open_amount="648.00", issue_date=date(2026, 3, 1), due_date=date(2026, 4, 1)
    )
    assert document.payments[0].paid_on == NOW.date()
