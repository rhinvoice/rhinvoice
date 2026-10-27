"""The document aggregate: quotes, invoices and cancellation invoices.

Content can only change while a document is a draft. From the moment it is
issued (invoices, cancellations) or sent (quotes), lines, tax rates, totals
and the company/customer/bank data are frozen (GoBD, OR 958f, BAO 131);
corrections are made with a cancellation invoice (Storno).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.document.calculation import CalculationInput, Totals, calculate
from rhinvoice.domain.document.lines import Discount, DocumentLine, LineKind, PriceMode
from rhinvoice.domain.document.write_off import WriteOff, WriteOffReason
from rhinvoice.domain.numbering.sequence import SequenceKind
from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Money
from rhinvoice.domain.shared.text import clean_multiline, clean_text
from rhinvoice.domain.tax.supply import line_treatment
from rhinvoice.domain.tax.treatment import TaxTreatment

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import datetime
    from decimal import Decimal
    from uuid import UUID

    from rhinvoice.domain.company.bank_account import BankAccount
    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.company.print_layout import PrintLayout
    from rhinvoice.domain.customer.customer import Customer
    from rhinvoice.domain.shared.country import Country
    from rhinvoice.domain.shared.language import Language
    from rhinvoice.domain.shared.money import Currency

MAX_LINES = 500
_NOT_FOR_GOODS = frozenset({TaxTreatment.EXPORT})
_SHA256 = re.compile(r"[0-9a-f]{64}")
MAX_SUBJECT = 200
MAX_REFERENCE = 100
MAX_TEXT = 4000
MAX_NOTE = 500
MAX_EVENT_DETAIL = 500
DEFAULT_QUOTE_VALIDITY = timedelta(days=30)


class DocumentType(StrEnum):
    QUOTE = "quote"
    INVOICE = "invoice"
    CANCELLATION = "cancellation"

    @property
    def sequence(self) -> SequenceKind:
        return SequenceKind(self.value)


class DocumentStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    ISSUED = "issued"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    CANCELLED = "cancelled"
    WRITTEN_OFF = "written_off"
    """Collecting the rest was given up; the invoice stays as issued (see ``WriteOff``)."""


class DisplayStatus(StrEnum):
    """Stored status plus the derived states "overdue" and "expired"."""

    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    ISSUED = "issued"
    PARTIALLY_PAID = "partially_paid"
    OVERDUE = "overdue"
    PAID = "paid"
    CANCELLED = "cancelled"
    WRITTEN_OFF = "written_off"


OPEN_INVOICE_STATUSES = frozenset({DocumentStatus.ISSUED, DocumentStatus.PARTIALLY_PAID})
MAX_NUMBER = 30


class DocumentOrigin(StrEnum):
    RHINVOICE = "rhinvoice"
    """Written and issued here."""
    IMPORTED = "imported"
    """Issued by a program used before and taken over with its original PDF (ADR 0019)."""


class EventKind(StrEnum):
    CREATED = "created"
    CREATED_FROM = "created_from"
    ISSUED = "issued"
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    CONVERTED = "converted"
    PAYMENT_ADDED = "payment_added"
    PAYMENT_REMOVED = "payment_removed"
    CANCELLED = "cancelled"
    TAX_OVERRIDDEN = "tax_overridden"
    REMINDED = "reminded"
    EMAILED = "emailed"
    """Sent by mail; the detail names the recipients."""
    REMINDER_EMAILED = "reminder_emailed"
    """A reminder of the invoice sent by mail; the detail is "<level> <recipients>"."""
    IMPORTED = "imported"
    """Taken over from a program used before; the detail names the original PDF."""
    FILE_ADDED = "file_added"
    """A file of an imported invoice added afterwards; the detail is its name."""
    WRITTEN_OFF = "written_off"
    """The open rest was written off; the detail is "<amount> <date> <reason>"."""
    WRITE_OFF_REMOVED = "write_off_removed"
    """The write-off was taken back; the detail is its amount."""


@dataclass(frozen=True, slots=True)
class DocumentEvent:
    at: datetime
    kind: EventKind
    detail: str = ""


@dataclass(frozen=True, slots=True)
class Payment:
    id: UUID
    paid_on: date
    amount: Money
    recorded_at: datetime
    note: str = ""

    def __post_init__(self) -> None:
        if self.amount.amount <= 0:
            raise ValidationError("amount", "a payment must be a positive amount")
        if self.amount != self.amount.round_to_minor():
            raise ValidationError("amount", "a payment has at most two decimal places")
        object.__setattr__(self, "note", clean_text(self.note, "note", max_length=MAX_NOTE))


@dataclass(frozen=True, slots=True)
class IssueSnapshot:
    """Company, customer and bank account exactly as they were when issuing."""

    company: Company
    customer: Customer
    bank_account: BankAccount | None
    notice: str | None = None
    """Legal notice of the tax treatment (e.g. reverse charge), in the wording of that day.

    None for documents issued before version 0.4, which did not store it.
    """
    layout: PrintLayout | None = None
    """The print layout of that day; None before version 0.5 (the current one is used)."""
    accounts: tuple[BankAccount, ...] | None = None
    """Every bank account of that day, for footers listing all; None before version 0.5."""
    goods_notice: str | None = None
    """Notice of the goods lines' own treatment (e.g. export delivery), when they have one."""


@dataclass(frozen=True, slots=True)
class DraftContent:
    """Everything a user can edit on a draft."""

    customer_id: UUID
    currency: Currency
    language: Language
    price_mode: PriceMode
    lines: tuple[DocumentLine, ...]
    treatment: TaxTreatment
    """Treatment of the document and its services."""
    treatment_overridden: bool = False
    discount: Discount = field(default_factory=Discount.none)
    issue_date: date | None = None
    due_date: date | None = None
    service_from: date | None = None
    service_to: date | None = None
    subject: str = ""
    reference: str = ""
    intro_text: str = ""
    payment_text: str = ""
    """Payment terms, printed after the totals."""
    closing_text: str = ""
    goods_treatment: TaxTreatment | None = None
    """Treatment of the goods lines; None: the document's (documents before 0.4)."""

    def __post_init__(self) -> None:
        if self.treatment.goods_only:
            raise ValidationError(
                "treatment_override",
                "goods get this treatment from reverse charge or an export",
                code="goods_only_treatment",
            )
        if self.goods_treatment in _NOT_FOR_GOODS:
            raise ValidationError("treatment_override", "this treatment does not apply to goods")
        if len(self.lines) > MAX_LINES:
            raise ValidationError("lines", f"a document has at most {MAX_LINES} lines")
        object.__setattr__(
            self, "subject", clean_text(self.subject, "subject", max_length=MAX_SUBJECT)
        )
        object.__setattr__(
            self, "reference", clean_text(self.reference, "reference", max_length=MAX_REFERENCE)
        )
        object.__setattr__(
            self, "intro_text", clean_multiline(self.intro_text, "intro_text", max_length=MAX_TEXT)
        )
        object.__setattr__(
            self,
            "payment_text",
            clean_multiline(self.payment_text, "payment_text", max_length=MAX_TEXT),
        )
        object.__setattr__(
            self,
            "closing_text",
            clean_multiline(self.closing_text, "closing_text", max_length=MAX_TEXT),
        )
        if self.service_from and self.service_to and self.service_from > self.service_to:
            raise ValidationError("service_to", "the service period ends before it starts")
        if self.issue_date and self.due_date and self.due_date < self.issue_date:
            raise ValidationError("due_date", "the due date is before the document date")

    @property
    def tax_date(self) -> date | None:
        """Date of supply; it decides the VAT rate (falls back to the document date)."""
        return self.service_to or self.service_from or self.issue_date

    def treatment_of(self, line: DocumentLine) -> TaxTreatment:
        return line_treatment(line.supply, self.treatment, self.goods_treatment)

    @property
    def treatments(self) -> tuple[TaxTreatment, ...]:
        """The treatments of the positions, the document's first; each with its notice."""
        found = dict.fromkeys(self.treatment_of(line) for line in self.lines if line.is_item)
        ordered = sorted(found, key=lambda treatment: treatment is not self.treatment)
        return tuple(ordered) or (self.treatment,)

    @property
    def charges_vat(self) -> bool:
        """Whether any position is taxed (then the rates are printed)."""
        return any(treatment.charges_vat for treatment in self.treatments)


@dataclass(frozen=True, slots=True)
class Document:
    id: UUID
    type: DocumentType
    status: DocumentStatus
    content: DraftContent
    created_at: datetime
    number: str | None = None
    issued_at: datetime | None = None
    snapshot: IssueSnapshot | None = None
    issued_totals: Totals | None = None
    payments: tuple[Payment, ...] = ()
    events: tuple[DocumentEvent, ...] = ()
    source_id: UUID | None = None
    """The quote an invoice was created from, or the invoice a cancellation cancels."""
    cancelled_by_id: UUID | None = None
    converted_to_id: UUID | None = None
    """The invoice a quote was turned into."""
    pdf_sha256: str | None = None
    """SHA-256 of the archived PDF, set once after issuing (GoBD, OR 958f)."""
    origin: DocumentOrigin = DocumentOrigin.RHINVOICE
    write_off: WriteOff | None = None
    """Set once collecting the open rest was given up; it stays when the rest is paid later."""

    # --- Factories -------------------------------------------------------------

    @classmethod
    def new_draft(
        cls,
        document_id: UUID,
        document_type: DocumentType,
        content: DraftContent,
        now: datetime,
        *,
        override_reason: str = "",
    ) -> Document:
        if document_type is DocumentType.CANCELLATION:
            raise ValidationError("type", "cancellations are created by cancelling an invoice")
        events = [DocumentEvent(now, EventKind.CREATED)]
        if content.treatment_overridden:
            events.append(_override_event(now, content, override_reason))
        return cls(
            id=document_id,
            type=document_type,
            status=DocumentStatus.DRAFT,
            content=content,
            created_at=now,
            events=tuple(events),
        )

    @classmethod
    def imported(  # noqa: PLR0913 - an invoice of another program is described by all of these
        cls,
        document_id: UUID,
        *,
        number: str,
        content: DraftContent,
        snapshot: IssueSnapshot,
        net: Money,
        total: Money,
        open_amount: Money,
        now: datetime,
        source: str = "",
    ) -> Document:
        """Take over an invoice another program issued, with the amounts it states.

        Its lines are not taken over: the original PDF is the invoice (``archive_pdf``).
        What was paid of it becomes one payment on the due date (at the latest today),
        since the program's payment dates are not known.
        """
        number = clean_text(number, "number", max_length=MAX_NUMBER, required=True)
        issue_date = content.issue_date
        if issue_date is None:
            raise ValidationError("issue_date", "issue_date is required")
        due_date = content.due_date or issue_date
        currency = content.currency
        if {net.currency, total.currency, open_amount.currency} != {currency}:
            raise ValidationError("currency", f"the amounts must be in {currency}")
        for field_name, amount in (("total", total), ("net", net), ("open_amount", open_amount)):
            if amount != amount.round_to_minor():
                raise ValidationError(field_name, "an amount has at most two decimal places")
        if not total.amount > 0:
            raise ValidationError(
                "total", "the total of an invoice must be positive", code="non_positive_total"
            )
        if net.amount < 0 or net > total:
            raise ValidationError(
                "net", "the net amount lies between zero and the total", code="net_above_total"
            )
        if open_amount.amount < 0 or open_amount > total:
            raise ValidationError(
                "open_amount",
                "the open amount lies between zero and the total",
                code="open_above_total",
            )
        # Written as amounts are ("8.00", not "8"), like the totals of invoices written here.
        net, total, open_amount = (
            net.round_to_minor(),
            total.round_to_minor(),
            open_amount.round_to_minor(),
        )
        zero = Money.zero(currency).round_to_minor()
        totals = Totals(
            currency=currency,
            lines=(),
            groups=(),
            subtotal=net,
            discount=zero,
            net=net,
            tax=total - net,
            gross=total,
            rounding=zero,
            total=total,
        )
        paid = total - open_amount
        # Paid by the due date, but not after the day of the import.
        paid_on = min(due_date, now.date())
        payments = (
            (Payment(id=new_id(), paid_on=paid_on, amount=paid, recorded_at=now),)
            if paid.amount > 0
            else ()
        )
        status = (
            DocumentStatus.PAID
            if not open_amount.amount
            else DocumentStatus.PARTIALLY_PAID
            if payments
            else DocumentStatus.ISSUED
        )
        return cls(
            id=document_id,
            type=DocumentType.INVOICE,
            status=status,
            content=replace(content, lines=(), due_date=due_date),
            created_at=now,
            number=number,
            issued_at=now,
            snapshot=snapshot,
            issued_totals=totals,
            payments=payments,
            events=(DocumentEvent(now, EventKind.IMPORTED, source[:MAX_EVENT_DETAIL]),),
            origin=DocumentOrigin.IMPORTED,
        )

    def copy_as_draft(
        self,
        document_id: UUID,
        document_type: DocumentType,
        now: datetime,
    ) -> Document:
        """Duplicate or convert (quote → invoice): same content, new draft, fresh dates."""
        self._require_own("copied")
        content = replace(
            self.content,
            lines=tuple(replace(line, id=new_id(), tax_rate=None) for line in self.content.lines),
            issue_date=None,
            due_date=None,
        )
        return replace(
            Document.new_draft(document_id, document_type, content, now),
            source_id=self.id if document_type is not self.type else None,
            events=(DocumentEvent(now, EventKind.CREATED_FROM, self.number or str(self.id)),),
        )

    # --- Queries -----------------------------------------------------------------

    @property
    def is_draft(self) -> bool:
        return self.status is DocumentStatus.DRAFT

    @property
    def is_imported(self) -> bool:
        return self.origin is DocumentOrigin.IMPORTED

    @property
    def cancellation_id(self) -> UUID:
        """The cancellation invoice of a cancelled invoice."""
        if self.cancelled_by_id is None:
            raise InvalidStateError("the document has not been cancelled")
        return self.cancelled_by_id

    @property
    def issued_number(self) -> str:
        if self.number is None:
            raise InvalidStateError("the document has no number yet")
        return self.number

    @property
    def issued_snapshot(self) -> IssueSnapshot:
        if self.snapshot is None:
            raise InvalidStateError("the document has not been issued yet")
        return self.snapshot

    @property
    def frozen_totals(self) -> Totals:
        """The totals fixed when issuing (or taken over with an imported invoice)."""
        if self.issued_totals is None:
            raise InvalidStateError("the document has not been issued yet")
        return self.issued_totals

    @property
    def paid_amount(self) -> Money:
        return sum((payment.amount for payment in self.payments), Money.zero(self.content.currency))

    def display_status(self, today: date) -> DisplayStatus:
        """Status for display; a cancellation invoice settles its invoice and is never late."""
        due = self.content.due_date
        late = due is not None and due < today and self.type is not DocumentType.CANCELLATION
        if self.status in OPEN_INVOICE_STATUSES and late:
            return DisplayStatus.OVERDUE
        if self.status is DocumentStatus.SENT and late:
            return DisplayStatus.EXPIRED
        return DisplayStatus(self.status.value)

    def totals(self, company_country: Country, *, cash_rounding: bool, today: date) -> Totals:
        """Frozen totals of issued documents, current ones of drafts.

        Drafts without service period or date use the rates valid ``today``,
        the date they would be issued on.
        """
        if self.issued_totals is not None:
            return self.issued_totals
        tax_date = self.content.tax_date or today

        def rate_for(line: DocumentLine) -> Decimal:
            if line.tax_rate is not None:
                return line.tax_rate
            return profile_of(company_country).rates_on(tax_date).rate(line.tax_category)

        return calculate(
            CalculationInput(
                currency=self.content.currency,
                price_mode=self.content.price_mode,
                lines=self.content.lines,
                discount=self.content.discount,
                treatment=self.content.treatment,
                rate_for=rate_for,
                cash_rounding=cash_rounding,
                goods_treatment=self.content.goods_treatment,
            ),
        )

    @property
    def recoveries(self) -> tuple[Payment, ...]:
        """Payments that came in after the invoice was written off."""
        write_off = self.write_off
        if write_off is None:
            return ()
        return tuple(
            payment for payment in self.payments if payment.recorded_at > write_off.recorded_at
        )

    @property
    def recovered_amount(self) -> Money:
        return sum(
            (payment.amount for payment in self.recoveries), Money.zero(self.content.currency)
        )

    @property
    def written_off_amount(self) -> Money:
        """What is lost of the invoice: the write-off less what was paid after it."""
        if self.write_off is None:
            return Money.zero(self.content.currency)
        return self.write_off.amount - self.recovered_amount

    def open_amount(self) -> Money:
        """Return what the customer is still expected to pay."""
        if self.issued_totals is None or self.status is DocumentStatus.CANCELLED:
            return Money.zero(self.content.currency)
        return self.issued_totals.total - self.paid_amount - self.written_off_amount

    # --- Commands ------------------------------------------------------------------

    def _require(self, *statuses: DocumentStatus, action: str) -> None:
        if self.status not in statuses:
            raise InvalidStateError(f"a {self.status} {self.type} cannot be {action}")

    def _require_invoice(self) -> None:
        """Refuse payments on anything but an invoice: a cancellation reverses its invoice."""
        if self.type is not DocumentType.INVOICE:
            raise InvalidStateError("only invoices are paid")

    def _require_own(self, action: str) -> None:
        """Refuse what needs lines: an imported invoice consists of its PDF."""
        if self.is_imported:
            raise InvalidStateError(
                f"an imported invoice cannot be {action}", code="imported_document"
            )

    def _with_event(
        self, now: datetime, kind: EventKind, detail: str = ""
    ) -> tuple[DocumentEvent, ...]:
        return (*self.events, DocumentEvent(now, kind, detail))

    def archive_pdf(self, sha256: str) -> Document:
        """Record the hash of the PDF that is kept as the issued document; only once."""
        if self.is_draft:
            raise InvalidStateError("drafts have no archived PDF")
        if self.pdf_sha256 is not None:
            raise InvalidStateError("the PDF of this document is already archived")
        if not _SHA256.fullmatch(sha256):
            raise ValidationError("pdf_sha256", "a SHA-256 hash has 64 lowercase hex digits")
        return replace(self, pdf_sha256=sha256)

    def record_file(self, file_name: str, now: datetime) -> Document:
        """Note a file added to an imported invoice (its PDF or an attachment)."""
        if not self.is_imported:
            raise InvalidStateError(
                "files are added to imported invoices only", code="not_imported"
            )
        return replace(
            self, events=self._with_event(now, EventKind.FILE_ADDED, file_name[:MAX_EVENT_DETAIL])
        )

    def edit(self, content: DraftContent, now: datetime, *, override_reason: str = "") -> Document:
        self._require(DocumentStatus.DRAFT, action="changed")
        events = self.events
        newly_overridden = content.treatment_overridden and (
            not self.content.treatment_overridden or content.treatment is not self.content.treatment
        )
        if newly_overridden:
            events = (*events, _override_event(now, content, override_reason))
        return replace(self, content=content, events=events)

    def issue(
        self,
        *,
        number: str,
        issue_date: date,
        due_date: date,
        snapshot: IssueSnapshot,
        now: datetime,
    ) -> Document:
        """Assign the number and freeze content, tax rates, totals and parties."""
        self._require(DocumentStatus.DRAFT, action="issued")
        if not any(line.kind is LineKind.ITEM for line in self.content.lines):
            raise ValidationError(
                "lines",
                "the document needs at least one position with an amount",
                code="no_positions",
            )
        if due_date < issue_date:
            raise ValidationError(
                "due_date", "the due date is before the document date", code="due_before_issue"
            )
        for problem in _reverse_charge_problems(self.content, snapshot.customer):
            raise problem
        company = snapshot.company
        tax_date = self.content.service_to or self.content.service_from or issue_date
        rates = profile_of(company.country).rates_on(tax_date)
        # Lines with a rate keep it: a cancellation reverses its invoice at the
        # invoice's rates, even when the rates changed in between.
        frozen_lines = tuple(
            replace(line, tax_rate=rates.rate(line.tax_category))
            if line.kind is LineKind.ITEM and line.tax_rate is None
            else line
            for line in self.content.lines
        )
        content = replace(
            self.content, lines=frozen_lines, issue_date=issue_date, due_date=due_date
        )
        issuing = replace(self, content=content)
        totals = issuing.totals(
            company.country, cash_rounding=company.cash_rounding, today=issue_date
        )
        if self.type is DocumentType.INVOICE and not totals.total.amount > 0:
            # Credits are cancellations; an invoice of zero or less could never be paid.
            raise ValidationError(
                "lines", "the total of an invoice must be positive", code="non_positive_total"
            )
        quote = self.type is DocumentType.QUOTE
        if self.type is DocumentType.INVOICE:
            profile_of(company.country).check_invoice(company, snapshot.customer, totals.total)
            if TaxTreatment.INTRA_COMMUNITY in content.treatments:
                for problem in _intra_community_problems(company, snapshot.customer):
                    raise problem
        return replace(
            issuing,
            status=DocumentStatus.SENT if quote else DocumentStatus.ISSUED,
            number=number,
            issued_at=now,
            snapshot=snapshot,
            issued_totals=totals,
            events=self._with_event(now, EventKind.SENT if quote else EventKind.ISSUED, number),
        )

    def issue_blockers(self, company: Company, customer: Customer, total: Money) -> tuple[str, ...]:
        """Codes of the company and customer details that issuing would still ask for.

        Issuing stops at the first; the editor lists them all, to be filled in before.
        """
        problems = list(_reverse_charge_problems(self.content, customer))
        if self.type is DocumentType.INVOICE:
            try:
                profile_of(company.country).check_invoice(company, customer, total)
            except ValidationError as error:
                problems.append(error)
            if TaxTreatment.INTRA_COMMUNITY in self.content.treatments:
                problems.extend(_intra_community_problems(company, customer))
        return tuple(problem.code for problem in problems)

    def accept(self, now: datetime) -> Document:
        self._require(DocumentStatus.SENT, action="accepted")
        return replace(
            self, status=DocumentStatus.ACCEPTED, events=self._with_event(now, EventKind.ACCEPTED)
        )

    def decline(self, now: datetime) -> Document:
        self._require(DocumentStatus.SENT, action="declined")
        return replace(
            self, status=DocumentStatus.DECLINED, events=self._with_event(now, EventKind.DECLINED)
        )

    def convert_check(self) -> None:
        """Only sent or accepted quotes become an invoice, and only once."""
        if self.type is not DocumentType.QUOTE:
            raise InvalidStateError("only quotes can be turned into invoices")
        self._require(DocumentStatus.SENT, DocumentStatus.ACCEPTED, action="turned into an invoice")
        if self.converted_to_id is not None:
            raise InvalidStateError(
                "this quote has already been turned into an invoice", code="already_converted"
            )

    def mark_converted(self, invoice_id: UUID, now: datetime) -> Document:
        """Record that a quote became an invoice; a sent quote counts as accepted."""
        self.convert_check()
        return replace(
            self,
            status=DocumentStatus.ACCEPTED,
            converted_to_id=invoice_id,
            events=self._with_event(now, EventKind.CONVERTED, str(invoice_id)),
        )

    def add_payment(self, payment: Payment, now: datetime) -> Document:
        """Record a payment; on a written-off invoice it takes back that much of the loss."""
        self._require(*OPEN_INVOICE_STATUSES, DocumentStatus.WRITTEN_OFF, action="paid")
        self._require_invoice()
        if payment.amount.currency is not self.content.currency:
            raise ValidationError("amount", f"the payment must be in {self.content.currency}")
        write_off = self.write_off
        if write_off is not None:
            # Payments recorded after the write-off take back the loss: both must be certain.
            if payment.recorded_at <= write_off.recorded_at:
                raise InvalidStateError(
                    "a payment of a written-off invoice is recorded after the write-off",
                    code="clock_went_back",
                )
            if payment.paid_on < write_off.written_off_on:
                raise ValidationError(
                    "paid_on",
                    "the payment is dated before the write-off; take the write-off back instead",
                    code="payment_dated_before_write_off",
                )
        unpaid = self.open_amount() + self.written_off_amount
        if payment.amount > unpaid:
            raise ValidationError(
                "amount",
                f"the payment exceeds the open amount of {unpaid}",
                code="payment_exceeds_open_amount",
            )
        if payment.amount == unpaid:
            status = DocumentStatus.PAID
        elif write_off is None:
            status = DocumentStatus.PARTIALLY_PAID
        else:
            status = DocumentStatus.WRITTEN_OFF
        return replace(
            self,
            payments=(*self.payments, payment),
            status=status,
            events=self._with_event(now, EventKind.PAYMENT_ADDED, _amount_detail(payment)),
        )

    def pay_in_full(self, payment_id: UUID, paid_on: date, now: datetime) -> Document:
        """Record a payment of the whole open amount."""
        self._require(*OPEN_INVOICE_STATUSES, action="paid")
        self._require_invoice()
        payment = Payment(
            id=payment_id, paid_on=paid_on, amount=self.open_amount(), recorded_at=now
        )
        return self.add_payment(payment, now)

    def remove_payment(self, payment_id: UUID, now: datetime) -> Document:
        self._require(
            DocumentStatus.PARTIALLY_PAID,
            DocumentStatus.PAID,
            DocumentStatus.WRITTEN_OFF,
            action="changed",
        )
        removed = next((payment for payment in self.payments if payment.id == payment_id), None)
        if removed is None:
            raise ValidationError("payment", "this payment does not belong to the document")
        payments = tuple(payment for payment in self.payments if payment.id != payment_id)
        if self.write_off is None:
            status = DocumentStatus.PARTIALLY_PAID if payments else DocumentStatus.ISSUED
        elif removed in self.recoveries:
            status = DocumentStatus.WRITTEN_OFF
        else:
            # The write-off names the rest after this payment; without it, it would be wrong.
            raise InvalidStateError(
                "remove the write-off before a payment made before it",
                code="payment_before_write_off",
            )
        return replace(
            self,
            payments=payments,
            status=status,
            events=self._with_event(now, EventKind.PAYMENT_REMOVED, _amount_detail(removed)),
        )

    def record_write_off(
        self,
        write_off_id: UUID,
        written_off_on: date,
        reason: WriteOffReason,
        now: datetime,
        *,
        note: str = "",
    ) -> Document:
        """Give up collecting the open rest; the invoice itself stays as issued."""
        self._require(*OPEN_INVOICE_STATUSES, action="written off")
        if self.type is not DocumentType.INVOICE:
            raise InvalidStateError("only invoices are written off")
        issue_date = self.content.issue_date
        if issue_date is not None and written_off_on < issue_date:
            raise ValidationError(
                "written_off_on",
                "an invoice is not written off before its date",
                code="write_off_before_invoice",
            )
        if any(payment.recorded_at > now for payment in self.payments):
            # Payments recorded later count as recovered: none may lie ahead of the clock.
            raise InvalidStateError(
                "a payment of the invoice was recorded after now", code="clock_went_back"
            )
        write_off = WriteOff(
            id=write_off_id,
            written_off_on=written_off_on,
            amount=self.open_amount(),
            reason=reason,
            recorded_at=now,
            note=note,
        )
        detail = f"{write_off.amount.amount:.2f} {written_off_on.isoformat()} {reason.value}"
        return replace(
            self,
            write_off=write_off,
            status=DocumentStatus.WRITTEN_OFF,
            events=self._with_event(now, EventKind.WRITTEN_OFF, detail),
        )

    def remove_write_off(self, now: datetime) -> Document:
        """Take a write-off back (it was a mistake): the rest is open again.

        Also for an invoice that was paid in full afterwards: it stays paid, and what
        came in counts as ordinary payments.
        """
        write_off = self.write_off
        if write_off is None or self.status not in {
            DocumentStatus.WRITTEN_OFF,
            DocumentStatus.PAID,
        }:
            raise InvalidStateError(f"a {self.status} {self.type} cannot be reopened")
        if self.status is DocumentStatus.PAID:
            status = DocumentStatus.PAID
        elif self.payments:
            status = DocumentStatus.PARTIALLY_PAID
        else:
            status = DocumentStatus.ISSUED
        return replace(
            self,
            write_off=None,
            status=status,
            events=self._with_event(
                now, EventKind.WRITE_OFF_REMOVED, f"{write_off.amount.amount:.2f}"
            ),
        )

    def record_reminder(self, level: int, now: datetime) -> Document:
        """Note a payment reminder of the given level in the history."""
        self._require(*OPEN_INVOICE_STATUSES, action="reminded")
        return replace(self, events=self._with_event(now, EventKind.REMINDED, str(level)))

    def record_mail(self, kind: EventKind, detail: str, now: datetime) -> Document:
        """Note in the history that the document (or a reminder of it) went out by mail."""
        if kind not in {EventKind.EMAILED, EventKind.REMINDER_EMAILED}:
            raise ValidationError("kind", "only mails are recorded this way")
        if self.is_draft:
            raise InvalidStateError("drafts are not sent; issue the document first")
        return replace(self, events=self._with_event(now, kind, detail[:MAX_EVENT_DETAIL]))

    def cancel_check(self) -> None:
        if self.type is not DocumentType.INVOICE:
            raise InvalidStateError("only invoices can be cancelled")
        self._require_own("cancelled")
        self._require(*OPEN_INVOICE_STATUSES, DocumentStatus.PAID, action="cancelled")
        if self.write_off is not None:
            # Paid after all, but the write-off still counts in its year: it goes first.
            raise InvalidStateError(
                "take the write-off back before cancelling the invoice", code="written_off"
            )

    def cancel(self, cancellation: Document, now: datetime) -> Document:
        """Mark this invoice as cancelled by an issued cancellation invoice."""
        self.cancel_check()
        if cancellation.source_id != self.id:
            raise InvalidStateError("the cancellation does not belong to this invoice")
        if (
            cancellation.issued_totals is None
            or self.issued_totals is None
            or cancellation.issued_totals.total != -self.issued_totals.total
        ):
            raise InvalidStateError("the cancellation must reverse the invoice exactly")
        return replace(
            self,
            status=DocumentStatus.CANCELLED,
            cancelled_by_id=cancellation.id,
            events=self._with_event(now, EventKind.CANCELLED, cancellation.issued_number),
        )

    def cancellation_draft(self, cancellation_id: UUID, now: datetime) -> Document:
        """Build a cancellation invoice with negated quantities, referring to this invoice."""
        self.cancel_check()
        negated = tuple(
            replace(line, id=new_id(), quantity=-line.quantity)
            if line.kind is LineKind.ITEM
            else replace(line, id=new_id())
            for line in self.content.lines
        )
        # The invoice's intro and payment terms ask for payment; a cancellation does not.
        content = replace(
            self.content,
            lines=negated,
            issue_date=None,
            due_date=None,
            intro_text="",
            payment_text="",
        )
        return Document(
            id=cancellation_id,
            type=DocumentType.CANCELLATION,
            status=DocumentStatus.DRAFT,
            content=content,
            created_at=now,
            source_id=self.id,
            events=(DocumentEvent(now, EventKind.CREATED_FROM, self.issued_number),),
        )

    def delete_check(self) -> None:
        """Only drafts may be deleted; issued documents are kept forever."""
        self._require(DocumentStatus.DRAFT, action="deleted")


def _reverse_charge_problems(
    content: DraftContent, customer: Customer
) -> Iterator[ValidationError]:
    if content.treatment is TaxTreatment.REVERSE_CHARGE and customer.vat_number is None:
        yield ValidationError(
            "treatment",
            "reverse charge needs the customer's VAT number",
            code="reverse_charge_needs_vat_number",
        )


def _intra_community_problems(company: Company, customer: Customer) -> Iterator[ValidationError]:
    """§ 14a Abs. 3 UStG (DE), Art. 11 Abs. 2 UStG (AT): both VAT IDs on the invoice."""
    if company.vat_number is None:
        yield ValidationError(
            "company",
            "an intra-Community supply states the VAT ID of the company",
            code="company_vat_id_missing",
        )
    if customer.vat_number is None:
        yield ValidationError(
            "customer_id",
            "an intra-Community supply states the VAT ID of the customer",
            code="customer_vat_id_missing",
        )


def _amount_detail(payment: Payment) -> str:
    """Plain decimal ("97.80"), formatted by the client in the document's currency."""
    return f"{payment.amount.amount:.2f}"


def _override_event(now: datetime, content: DraftContent, reason: str) -> DocumentEvent:
    """Log entry for a manually chosen tax treatment (CLAUDE.md §4)."""
    detail = f"{content.treatment}: {reason.strip()}" if reason.strip() else str(content.treatment)
    return DocumentEvent(now, EventKind.TAX_OVERRIDDEN, detail)


def default_due_date(
    document_type: DocumentType, issue_date: date, payment_terms_days: int
) -> date:
    if document_type is DocumentType.QUOTE:
        return issue_date + DEFAULT_QUOTE_VALIDITY
    if document_type is DocumentType.CANCELLATION:
        return issue_date
    return issue_date + timedelta(days=payment_terms_days)
