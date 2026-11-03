"""The list of issued invoices for the bookkeeping: period, rows, file names and sums."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rhinvoice.domain.document.attachment import Attachment
from rhinvoice.domain.document.document import (
    DisplayStatus,
    Document,
    DocumentType,
    Payment,
)
from rhinvoice.domain.document.export import (
    MAX_ENTRY_NAME,
    MAX_ENTRY_NAME_BYTES,
    MAX_PERIOD_YEARS,
    ExportListing,
    ExportPeriod,
    RateAmounts,
    export_listing,
    export_row,
    has_file,
    with_file_names,
)
from rhinvoice.domain.document.write_off import WriteOffReason
from rhinvoice.domain.shared.country import CountryCode
from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Currency, Money
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply
from rhinvoice.domain.tax.treatment import TaxTreatment
from rhinvoice.domain.tax.vat_number import VatNumber
from tests.helpers import raises_exactly
from tests.unit.domain import factories
from tests.unit.domain.test_document import NOW, TODAY, draft, issued, line, pay
from tests.unit.domain.test_imported_document import imported

MARCH = ExportPeriod.month(2026, 3)


def chf(value: str) -> Money:
    return Money(Decimal(value), Currency.CHF)


def eur(value: str) -> Money:
    return Money(Decimal(value), Currency.EUR)


def numbered(number: str, day: date = TODAY) -> Document:
    document = issued()
    return replace(document, number=number, content=replace(document.content, issue_date=day))


def cancelled(invoice: Document) -> tuple[Document, Document]:
    cancellation = invoice.cancellation_draft(new_id(), NOW).issue(
        number="S20260001",
        issue_date=TODAY,
        due_date=TODAY,
        snapshot=invoice.issued_snapshot,
        now=NOW,
    )
    return invoice.cancel(cancellation, NOW), cancellation


# --- Period ---------------------------------------------------------------------------


def test_periods_of_a_month_quarter_and_year() -> None:
    assert ExportPeriod(date(2026, 3, 1), date(2026, 3, 31)) == MARCH
    assert ExportPeriod.month(2026, 2).end == date(2026, 2, 28)
    assert ExportPeriod.month(2024, 2).end == date(2024, 2, 29)
    assert ExportPeriod.month(2026, 12) == ExportPeriod(date(2026, 12, 1), date(2026, 12, 31))
    assert ExportPeriod.previous_month(date(2026, 10, 29)) == ExportPeriod.month(2026, 9)
    assert ExportPeriod.previous_month(date(2026, 1, 1)) == ExportPeriod.month(2025, 12)
    assert ExportPeriod.previous_month(date(2026, 3, 31)) == ExportPeriod.month(2026, 2)


def test_a_period_starts_before_it_ends() -> None:
    assert ExportPeriod(TODAY, TODAY).contains(TODAY)
    with raises_exactly(ValidationError, "the period ends before it starts") as error:
        ExportPeriod(TODAY, TODAY - timedelta(days=1))
    assert error.value.code == "period_reversed"
    assert error.value.field == "end"


def test_a_period_spans_at_most_ten_years() -> None:
    assert MAX_PERIOD_YEARS == 10
    longest = ExportPeriod(date(2016, 1, 1), date(2025, 12, 31))
    assert longest.label == "2016-01-01_2025-12-31"
    with raises_exactly(ValidationError, "a period spans at most 10 years") as error:
        ExportPeriod(date(2016, 1, 1), date(2026, 1, 1))
    assert error.value.code == "period_too_long"
    assert error.value.field == "end"
    # From 29 February the limit is the 28th ten years later.
    ExportPeriod(date(2024, 2, 29), date(2034, 2, 27))
    with raises_exactly(ValidationError, "a period spans at most 10 years"):
        ExportPeriod(date(2024, 2, 29), date(2034, 2, 28))


def test_periods_at_the_end_of_the_calendar() -> None:
    last = ExportPeriod(date(9990, 1, 1), date(9999, 12, 31))
    assert last.label == "9990-01-01_9999-12-31"
    assert ExportPeriod.month(9999, 12).label == "9999-12"
    with raises_exactly(ValidationError, "a period spans at most 10 years"):
        ExportPeriod(date(9989, 12, 31), date(9999, 12, 31))


def test_a_period_contains_its_first_and_last_day() -> None:
    assert MARCH.contains(date(2026, 3, 1))
    assert MARCH.contains(date(2026, 3, 31))
    assert not MARCH.contains(date(2026, 2, 28))
    assert not MARCH.contains(date(2026, 4, 1))


@pytest.mark.parametrize(
    ("period", "label"),
    [
        (ExportPeriod.month(2026, 9), "2026-09"),
        (ExportPeriod.month(2026, 12), "2026-12"),
        (ExportPeriod(date(2026, 7, 1), date(2026, 9, 30)), "2026-Q3"),
        (ExportPeriod(date(2026, 1, 1), date(2026, 3, 31)), "2026-Q1"),
        (ExportPeriod(date(2026, 10, 1), date(2026, 12, 31)), "2026-Q4"),
        (ExportPeriod(date(2026, 1, 1), date(2026, 12, 31)), "2026"),
        # Whole months that are no quarter or year are named by their days.
        (ExportPeriod(date(2026, 2, 1), date(2026, 4, 30)), "2026-02-01_2026-04-30"),
        (ExportPeriod(date(2026, 2, 1), date(2027, 1, 31)), "2026-02-01_2027-01-31"),
        (ExportPeriod(date(2026, 1, 1), date(2026, 2, 28)), "2026-01-01_2026-02-28"),
        (ExportPeriod(date(2026, 9, 2), date(2026, 9, 30)), "2026-09-02_2026-09-30"),
        (ExportPeriod(date(2026, 9, 1), date(2026, 9, 29)), "2026-09-01_2026-09-29"),
        (ExportPeriod(date(2025, 12, 1), date(2026, 1, 31)), "2025-12-01_2026-01-31"),
    ],
)
def test_the_label_names_the_period_in_file_names(period: ExportPeriod, label: str) -> None:
    assert period.label == label


def test_the_period_selects_issued_invoices_and_cancellations_by_date() -> None:
    invoice, cancellation = cancelled(issued())
    assert MARCH.selects(invoice)
    assert MARCH.selects(cancellation)
    assert MARCH.selects(imported(issue_date=date(2026, 3, 1), due_date=date(2026, 3, 1)))
    assert not MARCH.selects(draft())
    assert not MARCH.selects(issued(DocumentType.QUOTE))
    assert not MARCH.selects(numbered("R1", date(2026, 4, 1)))
    assert not MARCH.selects(numbered("R1", date(2026, 2, 28)))


@given(
    start=st.dates(min_value=date(2000, 1, 1), max_value=date(2090, 12, 31)),
    days=st.integers(min_value=0, max_value=3700),
)
def test_a_valid_period_never_ends_before_it_starts(start: date, days: int) -> None:
    end = start + timedelta(days=days)
    leap_day = (start.month, start.day) == (2, 29)
    limit = start.replace(year=start.year + 10, day=28 if leap_day else start.day)
    if end >= limit:
        with pytest.raises(ValidationError, match="at most 10 years"):
            ExportPeriod(start, end)
        return
    period = ExportPeriod(start, end)
    assert period.contains(start)
    assert period.contains(end)


# --- Rows -----------------------------------------------------------------------------


def test_a_row_describes_an_issued_invoice() -> None:
    customer = factories.customer(
        number="1042",
        company_name="Beispiel AG",
        vat_number=VatNumber.parse("CHE-109.322.551 MWST"),
    )
    invoice = issued(service_from=date(2026, 2, 1), service_to=date(2026, 2, 28))
    invoice = replace(invoice, snapshot=replace(invoice.issued_snapshot, customer=customer))
    row = export_row(invoice, TODAY)
    assert row.document_id == invoice.id
    assert row.number == "R20260001"
    assert row.type is DocumentType.INVOICE
    assert row.issue_date == TODAY
    assert (row.service_from, row.service_to) == (date(2026, 2, 1), date(2026, 2, 28))
    assert row.customer_number == "1042"
    assert row.customer_name == "Beispiel AG"
    assert row.country == "CH"
    assert row.customer_vat_number == "CHE-109.322.551 MWST"
    assert row.currency is Currency.CHF
    assert row.treatments == (TaxTreatment.DOMESTIC,)
    # 10 x 150 at 8.1 %, 3 x 12.35 at 2.6 %.
    assert row.net == chf("1537.05")
    assert row.rates == (
        RateAmounts(Decimal("8.1"), chf("1500.00"), chf("121.50")),
        RateAmounts(Decimal("2.6"), chf("37.05"), chf("0.96")),
    )
    assert row.at_rate(Decimal("8.10")) == row.rates[0]
    assert row.at_rate(Decimal("7.7")) is None
    assert row.tax == chf("122.46")
    assert row.total == chf("1659.50")
    assert row.paid == chf("0")
    assert row.paid_on is None
    assert row.open == chf("1659.50")
    assert row.written_off is None
    assert row.status is DisplayStatus.ISSUED
    assert row.file_name is None


def test_a_row_without_vat_number_and_overdue() -> None:
    row = export_row(issued(), TODAY + timedelta(days=31))
    assert row.customer_vat_number == ""
    assert row.status is DisplayStatus.OVERDUE


def test_the_rates_of_a_row_add_up_groups_of_one_rate() -> None:
    lines = (
        line("1", "100", TaxCategory.STANDARD),
        line("1", "50", TaxCategory.STANDARD, Supply.GOODS),
        line("1", "10", TaxCategory.ZERO),
    )
    invoice = issued(
        lines=lines,
        treatment=TaxTreatment.EXPORT,
        goods_treatment=TaxTreatment.DOMESTIC,
    )
    row = export_row(invoice, TODAY)
    assert row.treatments == (TaxTreatment.EXPORT, TaxTreatment.DOMESTIC)
    # The export and the zero-rated line share the rate 0.
    assert row.rates == (
        RateAmounts(Decimal("8.1"), chf("50.00"), chf("4.05")),
        RateAmounts(Decimal(0), chf("110.00"), chf("0.00")),
    )


def test_paid_invoices_name_the_day_of_the_last_payment() -> None:
    invoice = pay(issued(), "600", date(2026, 3, 10))
    row = export_row(invoice, TODAY)
    assert row.paid == chf("600")
    assert row.paid_on is None
    assert row.open == chf("1059.50")
    assert row.status is DisplayStatus.PARTIALLY_PAID
    paid = pay(invoice, "1059.50", date(2026, 3, 12))
    row = export_row(paid, TODAY)
    assert row.paid == chf("1659.50")
    assert row.paid_on == date(2026, 3, 12)
    assert row.open == chf("0")
    assert row.status is DisplayStatus.PAID
    earlier = pay(pay(issued(), "1059.50", date(2026, 3, 12)), "600", date(2026, 3, 10))
    assert export_row(earlier, TODAY).paid_on == date(2026, 3, 12)


def test_written_off_invoices_name_what_is_lost() -> None:
    invoice = pay(issued(), "600").record_write_off(new_id(), TODAY, WriteOffReason.GONE, NOW)
    row = export_row(invoice, TODAY)
    assert row.written_off == chf("1059.50")
    assert row.open == chf("0")
    assert row.paid_on is None
    assert row.status is DisplayStatus.WRITTEN_OFF


def test_cancellations_are_negative_and_owe_nothing() -> None:
    invoice, cancellation = cancelled(pay(issued(), "100"))
    row = export_row(cancellation, TODAY)
    assert row.type is DocumentType.CANCELLATION
    assert row.number == "S20260001"
    assert row.net == chf("-1537.05")
    assert row.tax == chf("-122.46")
    assert row.total == chf("-1659.50")
    assert row.rates[0] == RateAmounts(Decimal("8.1"), chf("-1500.00"), chf("-121.50"))
    assert row.open == chf("0")
    assert row.paid == chf("0")
    assert row.status is DisplayStatus.ISSUED
    invoice_row = export_row(invoice, TODAY)
    assert invoice_row.status is DisplayStatus.CANCELLED
    assert invoice_row.open == chf("0")
    assert invoice_row.paid == chf("100")
    assert invoice_row.paid_on is None


def test_imported_invoices_have_no_rates() -> None:
    row = export_row(imported(open_amount="96.00"), TODAY)
    assert row.rates == ()
    assert row.net == chf("1200.00")
    assert row.tax == chf("96.00")
    assert row.total == chf("1296.00")
    assert row.paid == chf("1200.00")
    assert row.open == chf("96.00")


def test_a_row_needs_an_issued_document_with_a_date() -> None:
    with raises_exactly(InvalidStateError, "the document has not been issued yet"):
        export_row(draft(issue_date=TODAY), TODAY)
    invoice = issued()
    undated = replace(invoice, content=replace(invoice.content, issue_date=None))
    with raises_exactly(InvalidStateError, "the document has no date"):
        export_row(undated, TODAY)


# --- File names -----------------------------------------------------------------------


def test_files_are_named_after_the_number() -> None:
    rows = [
        export_row(numbered("R20260042"), TODAY),
        export_row(numbered("2026/7:a*b"), TODAY),
        export_row(numbered("r20260042"), TODAY),
        export_row(numbered("R20260042"), TODAY),
        export_row(numbered("R20260043"), TODAY),
    ]
    named = with_file_names(
        [(rows[0], True), (rows[1], True), (rows[2], True), (rows[3], True), (rows[4], False)]
    )
    assert [row.file_name for row in named] == [
        "R20260042.pdf",
        "2026-7-a-b.pdf",
        "r20260042 (2).pdf",
        "R20260042 (3).pdf",
        None,
    ]
    assert [row.number for row in named] == [row.number for row in rows]


def test_every_refused_character_is_replaced() -> None:
    row = export_row(numbered('a/b\\c:d*e?f"g<h>i|j'), TODAY)
    assert with_file_names([(row, True)])[0].file_name == "a-b-c-d-e-f-g-h-i-j.pdf"


def test_imported_invoices_have_a_file_only_with_their_pdf() -> None:
    assert has_file(issued())
    assert not has_file(imported())
    assert has_file(imported().archive_pdf("a" * 64))


# --- Listing --------------------------------------------------------------------------


def test_the_listing_holds_the_period_by_date_and_number() -> None:
    invoice, cancellation = cancelled(numbered("R20260002", date(2026, 3, 5)))
    later = numbered("R20260003", date(2026, 3, 20))
    first = numbered("R20260001", date(2026, 3, 5))
    documents = [
        later,
        invoice,
        draft(),
        issued(DocumentType.QUOTE),
        numbered("R20260009", date(2026, 4, 1)),
        cancellation,
        first,
        imported(issue_date=date(2026, 3, 31), due_date=date(2026, 3, 31)),
    ]
    listing = export_listing(MARCH, documents, TODAY, with_files=False)
    assert listing.period == MARCH
    assert not listing.with_files
    assert [(row.issue_date, row.number) for row in listing.rows] == [
        (date(2026, 3, 5), "R20260001"),
        (date(2026, 3, 5), "R20260002"),
        (date(2026, 3, 9), "S20260001"),
        (date(2026, 3, 20), "R20260003"),
        (date(2026, 3, 31), "R20150001"),
    ]
    assert all(row.file_name is None for row in listing.rows)


def test_with_files_each_row_with_a_pdf_names_it() -> None:
    documents = [numbered("R20260001"), imported(issue_date=TODAY, due_date=TODAY)]
    listing = export_listing(MARCH, documents, TODAY, with_files=True)
    assert listing.with_files
    assert [(row.number, row.file_name) for row in listing.rows] == [
        ("R20150001", None),
        ("R20260001", "R20260001.pdf"),
    ]


def test_the_rates_of_the_listing() -> None:
    reverse = issued(lines=(line("1", "100"),), treatment=TaxTreatment.EXPORT)
    listing = export_listing(
        MARCH,
        [issued(), reverse, imported(issue_date=TODAY, due_date=TODAY)],
        TODAY,
        with_files=False,
    )
    assert listing.rates == (Decimal("8.1"), Decimal("2.6"), Decimal(0))
    assert ExportListing(period=MARCH, rows=()).rates == ()
    assert ExportListing(period=MARCH, rows=()).sums == ()


def test_sums_per_currency_never_mix_currencies() -> None:
    euro_lines = (line("2", "50"),)
    paid = pay(issued(), "1659.50")
    written_off = pay(issued(), "659.50").record_write_off(
        new_id(), TODAY, WriteOffReason.GONE, NOW
    )
    invoice, cancellation = cancelled(issued())
    euro = issued(currency=Currency.EUR, lines=euro_lines)
    listing = export_listing(
        MARCH,
        [
            paid,
            written_off,
            invoice,
            cancellation,
            euro,
            imported(issue_date=TODAY, due_date=TODAY),
        ],
        TODAY,
        with_files=False,
    )
    franc, euros = listing.sums
    assert franc.currency is Currency.CHF
    assert franc.count == 5
    assert franc.net == chf("1537.05") * 3 - chf("1537.05") + chf("1200.00")
    assert franc.rates == (
        RateAmounts(Decimal("8.1"), chf("3000.00"), chf("243.00")),
        RateAmounts(Decimal("2.6"), chf("74.10"), chf("1.92")),
    )
    assert franc.at_rate(Decimal("2.6")) == franc.rates[1]
    assert franc.at_rate(Decimal(0)) is None
    assert franc.tax == chf("244.92") + chf("96.00")
    assert franc.total == chf("1659.50") * 2 + chf("1296.00")
    assert franc.paid == chf("1659.50") + chf("659.50") + chf("1296.00")
    assert franc.open == chf("0")
    assert franc.written_off == chf("1000.00")
    assert euros.currency is Currency.EUR
    assert euros.count == 1
    assert euros.net == eur("100.00")
    assert euros.rates == (RateAmounts(Decimal("8.1"), eur("100.00"), eur("8.10")),)
    assert euros.total == eur("108.10")
    assert euros.open == eur("108.10")
    assert euros.written_off == eur("0")
    assert euros.paid == eur("0")


def test_the_sum_of_the_customer_country() -> None:
    # The country is the one of the customer as issued.
    customer = factories.customer(address=factories.address(country=CountryCode("DE")))
    invoice = issued()
    invoice = replace(invoice, snapshot=replace(invoice.issued_snapshot, customer=customer))
    assert export_row(invoice, TODAY).country == "DE"


def test_payment_dates_of_imported_invoices() -> None:
    document = imported(issue_date=TODAY, due_date=TODAY)
    payment = document.payments[0]
    assert isinstance(payment, Payment)
    assert export_row(document, TODAY).paid_on == TODAY


def test_reserved_names_and_unicode_forms_are_taken() -> None:
    composed = export_row(numbered("Ré1"), TODAY)
    decomposed = export_row(numbered("Ré1"), TODAY)
    listed = export_row(numbered("Rechnungen 2026-03"), TODAY)
    named = with_file_names(
        [(composed, True), (decomposed, True), (listed, True)],
        reserved=["rechnungen 2026-03.PDF"],
    )
    assert [row.file_name for row in named] == [
        "Ré1.pdf",
        "Ré1 (2).pdf",
        "Rechnungen 2026-03 (2).pdf",
    ]
    listing = export_listing(MARCH, [numbered("L")], TODAY, with_files=True, reserved=["L.pdf"])
    assert listing.rows[0].file_name == "L (2).pdf"


# --- Pass-through items and attachments (ADR 0039, 0040) ------------------------------


def test_pass_through_items_are_neither_net_nor_tax() -> None:
    fee = line("1", "250.35", TaxCategory.PASS_THROUGH)
    invoice = issued(lines=(line(), fee))
    row = export_row(invoice, TODAY)
    assert row.net == chf("1500.00")
    assert row.tax == chf("121.50")
    assert row.pass_through == chf("250.35")
    assert row.total == chf("1871.85")
    assert row.rates == (RateAmounts(Decimal("8.1"), chf("1500.00"), chf("121.50")),)
    plain = issued()
    listing = export_listing(MARCH, [plain, invoice], TODAY, with_files=False)
    assert listing.has_pass_through
    [franc] = listing.sums
    assert franc.pass_through == chf("250.35")
    assert franc.total == chf("1659.50") + chf("1871.85")
    assert not export_listing(MARCH, [plain], TODAY, with_files=False).has_pass_through
    assert export_row(plain, TODAY).pass_through == chf("0")


def test_the_cash_rounding_makes_the_amounts_add_up_to_the_total() -> None:
    fee = line("1", "250.37", TaxCategory.PASS_THROUGH)
    rounded = issued(lines=(line(), fee))
    row = export_row(rounded, TODAY)
    assert row.rounding == chf("-0.02")
    assert row.total == chf("1871.85")
    assert row.net + row.tax + row.pass_through + row.rounding == row.total
    plain = issued(lines=(line(),))
    listing = export_listing(MARCH, [plain, rounded, rounded], TODAY, with_files=False)
    assert listing.has_rounding
    [franc] = listing.sums
    assert franc.rounding == chf("-0.04")
    assert not export_listing(MARCH, [plain], TODAY, with_files=False).has_rounding
    assert export_row(plain, TODAY).rounding == chf("0")


def test_attachments_follow_the_pdf_named_after_the_number() -> None:
    invoice = numbered("R20260042")
    other = numbered("R20260043")
    old = imported(issue_date=TODAY, due_date=TODAY).archive_pdf("a" * 64)

    def attachment(document: Document, name: str) -> Attachment:
        return Attachment(
            id=new_id(),
            document_id=document.id,
            file_name=name,
            sha256="b" * 64,
            size=1,
            added_at=NOW,
        )

    notary, office, twice = (
        attachment(invoice, "Notar.pdf"),
        attachment(invoice, "Amt: 3.pdf"),
        attachment(invoice, "notar.pdf"),
    )
    reminder = attachment(old, "Mahnung.pdf")
    listing = export_listing(
        MARCH,
        [invoice, other, old],
        TODAY,
        with_files=True,
        attachments={invoice.id: [notary, office, twice], old.id: [reminder]},
    )
    rows = {row.number: row for row in listing.rows}
    assert rows["R20260042"].file_name == "R20260042.pdf"
    assert rows["R20260042"].attachment_files == (
        (notary.id, "R20260042_Notar.pdf"),
        (office.id, "R20260042_Amt- 3.pdf"),
        (twice.id, "R20260042_notar (2).pdf"),
    )
    assert rows["R20260043"].attachment_files == ()
    # An imported invoice's further files stay in the archive.
    assert rows["R20150001"].attachment_files == ()
    without = export_listing(MARCH, [invoice], TODAY, with_files=True)
    assert without.rows[0].attachment_files == ()
    no_files = with_file_names([(export_row(invoice, TODAY), False)], (), {invoice.id: [notary]})
    assert no_files[0].attachment_files == ()


def test_long_attachment_names_are_shortened_in_the_zip() -> None:
    invoice = numbered("R20260042")

    def attachment(name: str) -> Attachment:
        return Attachment(new_id(), invoice.id, name, "b" * 64, 1, NOW)

    first, second = attachment("x" * 251 + ".pdf"), attachment("X" * 251 + ".pdf")
    spaced = attachment("y" * 184 + " ." + "z" * 60 + ".pdf")
    wide = attachment("a" + "ü" * 200 + ".pdf")
    kept = attachment("Notar .pdf")
    emoji = attachment("\U0001f4c4" * 100 + ".pdf")
    row = export_row(invoice, TODAY)
    [named] = with_file_names(
        [(row, True)], (), {invoice.id: [first, second, spaced, wide, emoji, kept]}
    )
    names = dict(named.attachment_files)
    assert names[first.id] == "R20260042_" + "x" * 186 + ".pdf"
    assert names[second.id] == "R20260042_" + "X" * 182 + " (2).pdf"
    # Shortened: no space or dot left before ".pdf".
    assert names[spaced.id] == "R20260042_" + "y" * 184 + ".pdf"
    # Two bytes each: 255 bytes before 200 characters.
    assert names[wide.id] == "R20260042_a" + "ü" * 120 + ".pdf"
    assert len(names[wide.id].encode()) == MAX_ENTRY_NAME_BYTES
    assert names[emoji.id] == "R20260042_" + "\U0001f4c4" * 60 + ".pdf"
    for name in names.values():
        assert len(name) <= MAX_ENTRY_NAME
        assert len(name.encode()) <= MAX_ENTRY_NAME_BYTES
    # Short names stay as they are.
    assert names[kept.id] == "R20260042_Notar .pdf"
    assert with_file_names([(row, True)])[0].file_name == "R20260042.pdf"
