"""The list of issued invoices for the bookkeeping or the tax adviser (ADR 0038).

A period holds the invoices (written here and imported) and the cancellation invoices
issued in it, by their issue date; never drafts or quotes. Amounts stay as they were
issued, so cancellations are negative. Sums are per currency: currencies are never added.
Pass-through items are neither net nor tax: they have a column of their own and are in the
total (ADR 0039).
"""

from __future__ import annotations

import unicodedata
from calendar import monthrange
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import TYPE_CHECKING

from rhinvoice.domain.document.document import (
    DisplayStatus,
    Document,
    DocumentStatus,
    DocumentType,
)
from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from rhinvoice.domain.shared.money import Money

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from decimal import Decimal
    from uuid import UUID

    from rhinvoice.domain.document.attachment import Attachment
    from rhinvoice.domain.shared.money import Currency
    from rhinvoice.domain.tax.treatment import TaxTreatment

MAX_PERIOD_YEARS = 10
MONTHS_PER_QUARTER = 3
EXPORTED_TYPES = frozenset({DocumentType.INVOICE, DocumentType.CANCELLATION})
REFUSED_IN_FILE_NAMES = '/\\:*?"<>|'


def _years_later(day: date, years: int) -> date:
    """Return the same day ``years`` later; 29 February becomes the 28th in a common year."""
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


def _month_end(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


@dataclass(frozen=True, slots=True)
class ExportPeriod:
    """The days whose issued documents are exported, both included."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValidationError("end", "the period ends before it starts", code="period_reversed")
        last_year = date.max.year - MAX_PERIOD_YEARS
        if self.start.year <= last_year and self.end >= _years_later(self.start, MAX_PERIOD_YEARS):
            raise ValidationError(
                "end",
                f"a period spans at most {MAX_PERIOD_YEARS} years",
                code="period_too_long",
            )

    @classmethod
    def month(cls, year: int, month: int) -> ExportPeriod:
        return cls(date(year, month, 1), _month_end(year, month))

    @classmethod
    def previous_month(cls, today: date) -> ExportPeriod:
        """Return the last full month before ``today``: the default of the export."""
        last = today.replace(day=1) - timedelta(days=1)
        return cls.month(last.year, last.month)

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end

    def selects(self, document: Document) -> bool:
        """Whether the document belongs to the export of this period."""
        issue_date = document.content.issue_date
        return (
            document.type in EXPORTED_TYPES
            and not document.is_draft
            and issue_date is not None
            and self.contains(issue_date)
        )

    @property
    def label(self) -> str:
        """The period in file names: 2026-09, 2026-Q3, 2026 or 2026-09-01_2026-10-15."""
        start, end = self.start, self.end
        if start.day == 1 and end == _month_end(end.year, end.month):
            months = (end.year - start.year) * 12 + end.month - start.month + 1
            if months == 1:
                return f"{start:%Y-%m}"
            if months == MONTHS_PER_QUARTER and start.month % MONTHS_PER_QUARTER == 1:
                return f"{start.year}-Q{start.month // MONTHS_PER_QUARTER + 1}"
            if months == 12 and start.month == 1:  # noqa: PLR2004 - months of a year
                return str(start.year)
        return f"{start.isoformat()}_{end.isoformat()}"


@dataclass(frozen=True, slots=True)
class RateAmounts:
    """What a document (or a currency's sum) holds at one VAT rate."""

    rate: Decimal
    net: Money
    tax: Money


@dataclass(frozen=True, slots=True)
class ExportRow:
    document_id: UUID
    number: str
    type: DocumentType
    issue_date: date
    service_from: date | None
    service_to: date | None
    customer_number: str
    customer_name: str
    country: str
    """ISO code of the customer's country, as issued."""
    customer_vat_number: str
    """Empty when the customer had none."""
    currency: Currency
    treatments: tuple[TaxTreatment, ...]
    net: Money
    rates: tuple[RateAmounts, ...]
    """Net and tax per rate, the highest rate first; none for imported invoices."""
    tax: Money
    pass_through: Money
    """Paid in the customer's name: outside net and tax, part of the total (ADR 0039)."""
    total: Money
    """The payable total, cash rounding included."""
    paid: Money
    paid_on: date | None
    """The day of the last payment of a paid invoice; None while anything is open."""
    open: Money
    written_off: Money | None
    """What is lost of a written-off invoice; None when it was not written off."""
    status: DisplayStatus
    file_name: str | None = None
    """The PDF's name in the ZIP; None without ZIP or when there is no PDF."""
    attachment_files: tuple[tuple[UUID, str], ...] = ()
    """The document's own attachments in the ZIP (ADR 0040): their id and name there."""

    def at_rate(self, rate: Decimal) -> RateAmounts | None:
        return next((amounts for amounts in self.rates if amounts.rate == rate), None)


def _rates(document: Document) -> tuple[RateAmounts, ...]:
    totals = document.frozen_totals
    zero = Money.zero(totals.currency)
    sums: dict[Decimal, tuple[Money, Money]] = {}
    for group in totals.groups:
        net, tax = sums.get(group.rate, (zero, zero))
        sums[group.rate] = (net + group.net, tax + group.tax)
    return tuple(
        RateAmounts(rate=rate, net=net, tax=tax)
        for rate, (net, tax) in sorted(sums.items(), key=lambda item: -item[0])
    )


def export_row(document: Document, today: date) -> ExportRow:
    """Describe an issued invoice or cancellation as a row of the list."""
    content = document.content
    issue_date = content.issue_date
    if issue_date is None:
        raise InvalidStateError("the document has no date")
    customer = document.issued_snapshot.customer
    totals = document.frozen_totals
    zero = Money.zero(content.currency)
    cancellation = document.type is DocumentType.CANCELLATION
    paid = document.status is DocumentStatus.PAID and document.payments
    return ExportRow(
        document_id=document.id,
        number=document.issued_number,
        type=document.type,
        issue_date=issue_date,
        service_from=content.service_from,
        service_to=content.service_to,
        customer_number=customer.number,
        customer_name=customer.display_name,
        country=customer.address.country.value,
        customer_vat_number="" if customer.vat_number is None else str(customer.vat_number),
        currency=content.currency,
        treatments=content.treatments,
        net=totals.net,
        rates=_rates(document),
        tax=totals.tax,
        pass_through=totals.pass_through,
        total=totals.total,
        paid=document.paid_amount,
        paid_on=max(payment.paid_on for payment in document.payments) if paid else None,
        # A cancellation settles its invoice; nobody owes or pays it.
        open=zero if cancellation else document.open_amount(),
        written_off=None if document.write_off is None else document.written_off_amount,
        status=document.display_status(today),
    )


def _file_name(number: str) -> str:
    return "".join("-" if character in REFUSED_IN_FILE_NAMES else character for character in number)


def with_file_names(
    rows: Iterable[tuple[ExportRow, bool]],
    reserved: Iterable[str] = (),
    attachments: Mapping[UUID, Sequence[Attachment]] | None = None,
) -> tuple[ExportRow, ...]:
    """Name the PDF of each row that has one after its number, e.g. "R20260042.pdf".

    Invoices and cancellations are numbered apart, and imported invoices bring numbers of
    their own: a name taken already (in any case and Unicode form, for file systems that
    ignore them) or ``reserved`` (the list beside the PDFs) gets " (2)", " (3)" and so on.
    The ``attachments`` of a document follow its PDF, named after the number and their own
    name, e.g. "R20260042_Notar.pdf".
    """

    def key(name: str) -> str:
        return unicodedata.normalize("NFC", name).casefold()

    taken = {key(name) for name in reserved}

    def free(base: str) -> str:
        name, count = f"{base}.pdf", 1
        while key(name) in taken:
            count += 1
            name = f"{base} ({count}).pdf"
        taken.add(key(name))
        return name

    named: list[ExportRow] = []
    for row, has_file in rows:
        if not has_file:
            named.append(row)
            continue
        base = _file_name(row.number)
        files = tuple(
            (attachment.id, free(f"{base}_{_file_name(attachment.file_name.removesuffix('.pdf'))}"))
            for attachment in (attachments or {}).get(row.document_id, ())
        )
        named.append(replace(row, file_name=free(base), attachment_files=files))
    return tuple(named)


@dataclass(frozen=True, slots=True)
class CurrencySum:
    currency: Currency
    count: int
    net: Money
    rates: tuple[RateAmounts, ...]
    tax: Money
    pass_through: Money
    total: Money
    paid: Money
    open: Money
    written_off: Money

    def at_rate(self, rate: Decimal) -> RateAmounts | None:
        return next((amounts for amounts in self.rates if amounts.rate == rate), None)


def _currency_sum(currency: Currency, rows: list[ExportRow]) -> CurrencySum:
    zero = Money.zero(currency)

    def total(values: Iterable[Money]) -> Money:
        return sum(values, zero)

    rates = sorted({amounts.rate for row in rows for amounts in row.rates}, reverse=True)
    return CurrencySum(
        currency=currency,
        count=len(rows),
        net=total(row.net for row in rows),
        rates=tuple(
            RateAmounts(
                rate=rate,
                net=total(found.net for row in rows if (found := row.at_rate(rate))),
                tax=total(found.tax for row in rows if (found := row.at_rate(rate))),
            )
            for rate in rates
        ),
        tax=total(row.tax for row in rows),
        pass_through=total(row.pass_through for row in rows),
        total=total(row.total for row in rows),
        paid=total(row.paid for row in rows),
        open=total(row.open for row in rows),
        written_off=total(row.written_off for row in rows if row.written_off is not None),
    )


@dataclass(frozen=True, slots=True)
class ExportListing:
    period: ExportPeriod
    rows: tuple[ExportRow, ...]
    with_files: bool = False
    """Whether the PDFs come along (ZIP): then the list names each one's file."""

    @property
    def rates(self) -> tuple[Decimal, ...]:
        """The VAT rates occurring in the list, the highest first."""
        return tuple(
            sorted({amounts.rate for row in self.rows for amounts in row.rates}, reverse=True)
        )

    @property
    def has_pass_through(self) -> bool:
        """Whether any document holds pass-through items: only then they get a column."""
        return any(row.pass_through.amount for row in self.rows)

    @property
    def sums(self) -> tuple[CurrencySum, ...]:
        """One sum per currency, in the order of the currency codes."""
        currencies = sorted({row.currency for row in self.rows})
        return tuple(
            _currency_sum(currency, [row for row in self.rows if row.currency is currency])
            for currency in currencies
        )


def has_file(document: Document) -> bool:
    """Whether a PDF can be added: always for own documents, imported ones need theirs."""
    return not document.is_imported or document.pdf_sha256 is not None


def export_listing(  # noqa: PLR0913 - the period, its documents and what the ZIP holds
    period: ExportPeriod,
    documents: Iterable[Document],
    today: date,
    *,
    with_files: bool,
    reserved: Iterable[str] = (),
    attachments: Mapping[UUID, Sequence[Attachment]] | None = None,
) -> ExportListing:
    """List the documents of the period by date, then number; no PDF is named ``reserved``.

    With files, the ``attachments`` of own documents come along after each one's PDF; an
    imported invoice's further files stay in the archive.
    """
    selected = [document for document in documents if period.selects(document)]
    rows = sorted(
        ((export_row(document, today), with_files and has_file(document)) for document in selected),
        key=lambda found: (found[0].issue_date, found[0].number),
    )
    own = {
        document.id: (attachments or {}).get(document.id, ())
        for document in selected
        if not document.is_imported
    }
    return ExportListing(
        period=period,
        rows=with_file_names(rows, reserved, own),
        with_files=with_files,
    )
