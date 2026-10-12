"""Use cases for quotes, invoices and cancellation invoices."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import TYPE_CHECKING

from rhinvoice.application.backup.ports import BackupReason
from rhinvoice.application.document.ports import DocumentIndex
from rhinvoice.application.errors import NotFoundError
from rhinvoice.application.numbering.handlers import allocate_number
from rhinvoice.application.text.handlers import effective_notice
from rhinvoice.domain.catalog.unit import Unit
from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.document.attachment import Attachment
from rhinvoice.domain.document.document import (
    DisplayStatus,
    Document,
    DocumentType,
    DraftContent,
    IssueSnapshot,
    Payment,
    default_due_date,
)
from rhinvoice.domain.document.lines import (
    Discount,
    DiscountKind,
    DocumentLine,
    LineKind,
    PriceMode,
)
from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Currency, Money, parse_decimal
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply
from rhinvoice.domain.tax.treatment import (
    TaxContext,
    TaxTreatment,
    determine_treatment,
    goods_treatment,
    vat_number_would_reverse_charge,
)
from rhinvoice.domain.text.template import TextKind

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import date
    from uuid import UUID

    from rhinvoice.application.common import Page
    from rhinvoice.application.document.ports import (
        DocumentFacets,
        DocumentQuery,
        DocumentSummary,
    )
    from rhinvoice.application.uow import UnitOfWork, UnitOfWorkFactory
    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.customer.customer import Customer
    from rhinvoice.domain.document.calculation import Totals
    from rhinvoice.domain.shared.clock import Clock
    from rhinvoice.domain.shared.language import Language
    from rhinvoice.domain.text.template import TextTemplate


MAX_ADDED_FILE_BYTES = 20 * 1024 * 1024
"""A PDF added to an imported invoice; scans of many pages stay below."""


@dataclass(frozen=True, slots=True)
class LineInput:
    kind: LineKind
    description: str
    details: str = ""
    quantity: str = "1"
    unit: str | None = None
    unit_price: str = "0"
    discount_percent: str = "0"
    tax_category: TaxCategory = TaxCategory.STANDARD
    supply: Supply = Supply.SERVICE
    article_id: UUID | None = None

    def to_domain(self, index: int) -> DocumentLine:
        prefix = f"lines.{index}"
        try:
            return DocumentLine(
                id=new_id(),
                kind=self.kind,
                description=self.description,
                details=self.details,
                quantity=parse_decimal(self.quantity, "quantity"),
                unit=None if self.kind is LineKind.TEXT or self.unit is None else Unit(self.unit),
                unit_price=parse_decimal(self.unit_price, "unit_price"),
                discount_percent=parse_decimal(self.discount_percent, "discount_percent"),
                tax_category=self.tax_category,
                supply=self.supply,
                article_id=self.article_id,
            )
        except ValidationError as error:
            raise ValidationError(f"{prefix}.{error.field}", error.message) from None


@dataclass(frozen=True, slots=True)
class DraftInput:
    customer_id: UUID
    currency: Currency | None = None
    """None: the customer's or the company's default currency."""
    language: Language | None = None
    price_mode: PriceMode = PriceMode.NET
    lines: tuple[LineInput, ...] = ()
    discount_kind: DiscountKind = DiscountKind.PERCENT
    discount_value: str | None = None
    """None: the customer's default discount."""
    treatment_override: TaxTreatment | None = None
    override_reason: str = ""
    issue_date: date | None = None
    due_date: date | None = None
    service_from: date | None = None
    service_to: date | None = None
    subject: str = ""
    reference: str = ""
    intro_text: str = ""
    payment_text: str = ""
    closing_text: str = ""


@dataclass(frozen=True, slots=True)
class PaymentInput:
    paid_on: date
    amount: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class DocumentView:
    document: Document
    totals: Totals
    customer: Customer | None
    """Current customer data (drafts); issued documents use their snapshot."""
    display_status: DisplayStatus
    notices: tuple[tuple[TaxTreatment, str], ...]
    """Legal notice per treatment of the positions (services first, then goods).

    Frozen once issued, the current wording for drafts; "" where none is needed.
    """
    company: Company
    """The current company (issued documents print their snapshot)."""

    @property
    def notice(self) -> str:
        """All notices of the document, one per line."""
        return "\n".join(text for _, text in self.notices if text)

    def notice_of(self, treatment: TaxTreatment) -> str:
        return next((text for found, text in self.notices if found is treatment), "")


@dataclass(frozen=True, slots=True)
class DocumentPreview:
    view: DocumentView
    rates: dict[TaxCategory, Decimal]
    """Rate per tax category that the draft's lines would get, for the line selects."""
    customer_vat_missing: bool = False
    """The customer is an EU business without a VAT number: with one, reverse charge."""


def _customer_name(document: Document, customer: Customer | None) -> str:
    if document.snapshot is not None:
        return document.snapshot.customer.display_name
    return "" if customer is None else customer.display_name


def build_index(document: Document, totals: Totals, customer: Customer | None) -> DocumentIndex:
    name = _customer_name(document, customer)
    content = document.content
    texts = [
        document.number or "",
        name,
        content.subject,
        content.reference,
        *(line.description for line in content.lines),
        *(line.details for line in content.lines),
    ]
    open_amount = document.open_amount() if document.issued_totals is not None else totals.total
    return DocumentIndex(
        customer_name=name,
        net=totals.net,
        total=totals.total,
        open_amount=open_amount,
        search_text=" ".join(text for text in texts if text),
    )


@dataclass(frozen=True, slots=True)
class RecordedPayment:
    """A payment recorded by a bulk action, kept to undo it."""

    document_id: UUID
    payment_id: UUID


@dataclass(frozen=True, slots=True)
class DocumentHandlers:
    uow: UnitOfWorkFactory
    clock: Clock

    # --- Reading ---------------------------------------------------------------

    def search(self, query: DocumentQuery) -> Page[DocumentSummary]:
        with self.uow() as uow:
            return uow.documents.search(query)

    def facets(self, query: DocumentQuery) -> DocumentFacets:
        with self.uow() as uow:
            return uow.documents.facets(query)

    def get(self, document_id: UUID) -> DocumentView:
        with self.uow() as uow:
            document = self._require(uow, document_id)
            return self._view(uow, document)

    # --- Drafts ------------------------------------------------------------------

    def create(self, document_type: DocumentType, draft: DraftInput) -> DocumentView:
        with self.uow() as uow:
            company = self._company(uow)
            customer = self._customer(uow, draft.customer_id)
            content = self._content(company, customer, draft, previous=None)
            document = Document.new_draft(
                new_id(),
                document_type,
                content,
                self.clock.now(),
                override_reason=draft.override_reason,
            )
            view = self._save(uow, document, new=True)
            uow.commit()
        return view

    def preview(self, document_type: DocumentType, draft: DraftInput) -> DocumentPreview:
        """Calculate a draft without saving it, for live totals in the editor."""
        with self.uow() as uow:
            company = self._company(uow)
            customer = self._customer(uow, draft.customer_id)
            content = self._content(company, customer, draft, previous=None)
            document = Document.new_draft(new_id(), document_type, content, self.clock.now())
            rates = profile_of(company.country).rates_on(content.tax_date or self.clock.today())
            available: dict[TaxCategory, Decimal] = {}
            for category in TaxCategory:
                try:
                    rate = rates.rate(category)
                except ValidationError:
                    continue  # e.g. no special rate in Germany
                available[category] = rate if content.treatment.charges_vat else Decimal(0)
            return DocumentPreview(
                view=self._view(uow, document),
                rates=available,
                # A treatment chosen by hand needs no hint about the automatic one.
                customer_vat_missing=draft.treatment_override is None
                and vat_number_would_reverse_charge(_tax_context(company, customer)),
            )

    def update(self, document_id: UUID, draft: DraftInput) -> DocumentView:
        with self.uow() as uow:
            document = self._require(uow, document_id, for_update=True)
            company = self._company(uow)
            customer = self._customer(uow, draft.customer_id)
            content = self._content(company, customer, draft, previous=document.content)
            document = document.edit(
                content, self.clock.now(), override_reason=draft.override_reason
            )
            view = self._save(uow, document, new=False)
            uow.commit()
        return view

    def delete(self, document_id: UUID) -> None:
        with self.uow() as uow:
            self._require(uow, document_id, for_update=True).delete_check()
            uow.documents.delete(document_id)
            uow.commit()

    def duplicate(self, document_id: UUID) -> DocumentView:
        with self.uow() as uow:
            source = self._require(uow, document_id)
            if source.type is DocumentType.CANCELLATION:
                raise InvalidStateError("cancellation invoices cannot be duplicated")
            copy = source.copy_as_draft(new_id(), source.type, self.clock.now())
            view = self._save(uow, copy, new=True)
            uow.commit()
        return view

    def convert_to_invoice(self, quote_id: UUID) -> DocumentView:
        with self.uow() as uow:
            quote = self._require(uow, quote_id, for_update=True)
            quote.convert_check()
            invoice = quote.copy_as_draft(new_id(), DocumentType.INVOICE, self.clock.now())
            invoice = replace(
                invoice,
                content=_invoice_texts(
                    invoice.content, uow.text_templates.list(), invoice.content.language
                ),
            )
            quote = quote.mark_converted(invoice.id, self.clock.now())
            # The invoice first: the quote refers to it.
            view = self._save(uow, invoice, new=True)
            self._save(uow, quote, new=False)
            uow.commit()
        return view

    # --- Lifecycle ------------------------------------------------------------------

    def issue(self, document_id: UUID) -> DocumentView:
        with self.uow() as uow:
            document = self._require(uow, document_id, for_update=True)
            document = self._issue(uow, document)
            view = self._save(uow, document, new=False)
            uow.commit()
        return view

    def accept(self, quote_id: UUID) -> DocumentView:
        return self._change(quote_id, lambda document: document.accept(self.clock.now()))

    def decline(self, quote_id: UUID) -> DocumentView:
        return self._change(quote_id, lambda document: document.decline(self.clock.now()))

    def cancel(self, invoice_id: UUID) -> DocumentView:
        """Issue a cancellation invoice for an invoice and mark the invoice cancelled."""
        with self.uow() as uow:
            invoice = self._require(uow, invoice_id, for_update=True)
            # Validates first, so no cancellation number is used up for a refused cancel.
            draft = invoice.cancellation_draft(new_id(), self.clock.now())
            # Saved as a draft first like every document: lines may only be written
            # while a document is a draft (enforced by a database trigger).
            self._save(uow, draft, new=True)
            # Same issuer, recipient and rounding as the invoice it reverses.
            original = replace(invoice.issued_snapshot, bank_account=None)
            cancellation = self._issue(uow, draft, snapshot=original)
            self._save(uow, cancellation, new=False)
            invoice = invoice.cancel(cancellation, self.clock.now())
            view = self._save(uow, invoice, new=False)
            uow.commit()
        return view

    def add_payment(self, document_id: UUID, payment: PaymentInput) -> DocumentView:
        self._check_payment_date(payment.paid_on)

        def apply(document: Document) -> Document:
            amount = Money(parse_decimal(payment.amount, "amount"), document.content.currency)
            return document.add_payment(
                Payment(
                    id=new_id(),
                    paid_on=payment.paid_on,
                    amount=amount,
                    recorded_at=self.clock.now(),
                    note=payment.note,
                ),
                self.clock.now(),
            )

        return self._change(document_id, apply)

    def mark_paid(self, document_id: UUID, paid_on: date) -> DocumentView:
        """Record a payment of the whole open amount."""
        self._check_payment_date(paid_on)
        return self._change(
            document_id,
            lambda document: document.pay_in_full(new_id(), paid_on, self.clock.now()),
        )

    def mark_paid_many(
        self, document_ids: Sequence[UUID], paid_on: date | None = None
    ) -> list[RecordedPayment]:
        """Record full payments of several invoices at once: all of them or none.

        Without a date the payments are dated today (in the installation's time zone).
        """
        paid_on = paid_on or self.clock.today()
        self._check_payment_date(paid_on)
        recorded: list[RecordedPayment] = []
        with self.uow() as uow:
            # Locking in a fixed order keeps two concurrent bulk actions from deadlocking.
            for document_id in sorted(set(document_ids)):
                payment_id = new_id()
                document = self._require(uow, document_id, for_update=True)
                try:
                    paid = document.pay_in_full(payment_id, paid_on, self.clock.now())
                except InvalidStateError as error:
                    # Name the invoice that stops the batch.
                    number = document.number or str(document.id)
                    raise InvalidStateError(
                        f"{number}: {error.message}",
                        details={"document": number},
                        code="cannot_mark_paid",
                    ) from error
                self._save(uow, paid, new=False)
                recorded.append(RecordedPayment(document_id=document_id, payment_id=payment_id))
            uow.commit()
        return recorded

    def remove_payments(self, payments: Sequence[RecordedPayment]) -> None:
        """Undo several payments at once (e.g. a bulk "paid"): all of them or none."""
        with self.uow() as uow:
            for item in sorted(set(payments), key=lambda payment: payment.document_id):
                document = self._require(uow, item.document_id, for_update=True)
                if all(payment.id != item.payment_id for payment in document.payments):
                    raise NotFoundError("payment not found")
                self._save(
                    uow, document.remove_payment(item.payment_id, self.clock.now()), new=False
                )
            uow.commit()

    def remove_payment(self, document_id: UUID, payment_id: UUID) -> DocumentView:
        def apply(document: Document) -> Document:
            if all(payment.id != payment_id for payment in document.payments):
                raise NotFoundError("payment not found")
            return document.remove_payment(payment_id, self.clock.now())

        return self._change(document_id, apply)

    # --- Files of imported invoices ------------------------------------------------------

    def attachments(self, document_id: UUID) -> list[Attachment]:
        with self.uow() as uow:
            self._require(uow, document_id)
            return uow.documents.attachments(document_id)

    def attachment(self, document_id: UUID, attachment_id: UUID) -> tuple[Attachment, bytes]:
        with self.uow() as uow:
            found = uow.documents.get_attachment(document_id, attachment_id)
        if found is None:
            raise NotFoundError("attachment not found")
        return found

    def add_file(self, document_id: UUID, file_name: str, content: bytes) -> DocumentView:
        """Add a PDF to an imported invoice: its original if it has none, else an attachment.

        Neither can be replaced or removed afterwards (GoBD, OR 958f).
        """
        if not content.startswith(b"%PDF-"):
            raise ValidationError("file", "the file is no PDF", code="not_a_pdf")
        if len(content) > MAX_ADDED_FILE_BYTES:
            raise ValidationError("file", "the file is larger than 20 MB", code="file_too_large")
        sha256 = hashlib.sha256(content).hexdigest()
        now = self.clock.now()
        with self.uow() as uow:
            document = self._require(uow, document_id, for_update=True).record_file(file_name, now)
            if document.pdf_sha256 is None:
                document = document.archive_pdf(sha256)
                view = self._save(uow, document, new=False)
                uow.documents.archive_pdf(document, content)
            else:
                view = self._save(uow, document, new=False)
                attachment = Attachment(
                    id=new_id(),
                    document_id=document_id,
                    file_name=file_name,
                    sha256=sha256,
                    size=len(content),
                    added_at=now,
                )
                uow.documents.add_attachment(attachment, content)
            uow.commit()
        return view

    # --- Helpers ------------------------------------------------------------------------

    def _check_payment_date(self, paid_on: date) -> None:
        if paid_on > self.clock.today():
            raise ValidationError(
                "paid_on", "the payment date is in the future", code="payment_date_in_future"
            )

    def _change(self, document_id: UUID, change: Callable[[Document], Document]) -> DocumentView:
        with self.uow() as uow:
            document = change(self._require(uow, document_id, for_update=True))
            view = self._save(uow, document, new=False)
            uow.commit()
        return view

    def _issue(
        self, uow: UnitOfWork, document: Document, *, snapshot: IssueSnapshot | None = None
    ) -> Document:
        """Issue under the sequence lock; ``snapshot`` overrides the current parties."""
        company = self._company(uow)
        customer = self._customer(uow, document.content.customer_id)
        currency = document.content.currency
        account = next(
            (a for a in uow.bank_accounts.list() if a.currency is currency and a.is_default),
            None,
        )
        if account is None and document.type is DocumentType.INVOICE:
            raise ValidationError(
                "currency",
                f"please add a bank account for {currency} before issuing invoices in {currency}",
                code="bank_account_missing",
            )
        today = self.clock.today()
        issue_date = document.content.issue_date or today
        if issue_date > today:
            raise ValidationError(
                "issue_date", "the document date is in the future", code="issue_date_in_future"
            )
        # Numbers must follow the dates: no document before the last issued one.
        latest = uow.documents.latest_issue_date(document.type)
        if latest is not None and issue_date < latest:
            raise ValidationError(
                "issue_date",
                f"the document date is before the last issued document ({latest.isoformat()})",
                code="issue_date_before_last",
            )
        if document.type is not DocumentType.CANCELLATION:
            # The customer may have changed since the draft was saved.
            document = replace(
                document,
                content=_with_treatments(document.content, company, customer),
            )
        terms = customer.payment_terms_days
        due_date = document.content.due_date or default_due_date(
            document.type,
            issue_date,
            company.payment_terms_days if terms is None else terms,
        )
        number = allocate_number(uow, document.type.sequence, issue_date)
        if snapshot is None:
            snapshot = IssueSnapshot(
                company=company,
                customer=customer,
                bank_account=account,
                notice=effective_notice(
                    uow, document.content.treatment, company.country, document.content.language
                ),
                layout=uow.company.print_layout(),
                accounts=tuple(uow.bank_accounts.list()),
                goods_notice=_goods_notice(uow, document.content, company),
            )
        issued = document.issue(
            number=number,
            issue_date=issue_date,
            due_date=due_date,
            snapshot=snapshot,
            now=self.clock.now(),
        )
        # Committed together with the document: a refused issue requests nothing.
        uow.backups.request(BackupReason.DOCUMENT, self.clock.now())
        return issued

    def _content(
        self,
        company: Company,
        customer: Customer,
        draft: DraftInput,
        *,
        previous: DraftContent | None,
    ) -> DraftContent:
        currency = draft.currency or customer.default_currency or company.default_currency
        if previous is not None and draft.discount_value is None:
            discount = previous.discount
        else:
            value = draft.discount_value
            discount = Discount(
                draft.discount_kind,
                customer.default_discount if value is None else parse_decimal(value, "discount"),
            )
        treatment = draft.treatment_override or _treatment(company, customer)
        overridden = draft.treatment_override is not None
        return DraftContent(
            customer_id=customer.id,
            currency=currency,
            language=draft.language or customer.default_language or company.default_language,
            price_mode=draft.price_mode,
            lines=tuple(line.to_domain(index) for index, line in enumerate(draft.lines)),
            treatment=treatment,
            treatment_overridden=overridden,
            goods_treatment=_goods_treatment(treatment, company, customer, overridden=overridden),
            discount=discount,
            issue_date=draft.issue_date,
            due_date=draft.due_date,
            service_from=draft.service_from,
            service_to=draft.service_to,
            subject=draft.subject,
            reference=draft.reference,
            intro_text=draft.intro_text,
            payment_text=draft.payment_text,
            closing_text=draft.closing_text,
        )

    def _view(self, uow: UnitOfWork, document: Document) -> DocumentView:
        company = self._company(uow)
        customer = uow.customers.get(document.content.customer_id)
        totals = document.totals(
            company.country, cash_rounding=company.cash_rounding, today=self.clock.today()
        )
        content = document.content
        snapshot = None if document.is_draft else document.issued_snapshot
        notices: list[tuple[TaxTreatment, str]] = []
        for treatment in content.treatments:
            frozen = None
            if snapshot is not None:
                frozen = (
                    snapshot.notice if treatment is content.treatment else snapshot.goods_notice
                )
            # Drafts, and documents issued before notices were stored, use today's wording.
            text = (
                effective_notice(uow, treatment, company.country, content.language)
                if frozen is None
                else frozen
            )
            notices.append((treatment, text))
        return DocumentView(
            document=document,
            totals=totals,
            customer=customer,
            display_status=document.display_status(self.clock.today()),
            notices=tuple(notices),
            company=company,
        )

    def save_in(self, uow: UnitOfWork, document: Document) -> DocumentView:
        """Save a changed document within another use case's unit of work."""
        return self._save(uow, document, new=False)

    def _save(self, uow: UnitOfWork, document: Document, *, new: bool) -> DocumentView:
        view = self._view(uow, document)
        index = build_index(document, view.totals, view.customer)
        if new:
            uow.documents.add(document, index)
        else:
            uow.documents.update(document, index)
        return view

    @staticmethod
    def _company(uow: UnitOfWork) -> Company:
        company = uow.company.get()
        if company is None:
            raise ValidationError("company", "please set up the company before creating documents")
        return company

    @staticmethod
    def _customer(uow: UnitOfWork, customer_id: UUID) -> Customer:
        customer = uow.customers.get(customer_id)
        if customer is None:
            raise ValidationError("customer_id", "the customer does not exist")
        return customer

    @staticmethod
    def _require(uow: UnitOfWork, document_id: UUID, *, for_update: bool = False) -> Document:
        document = uow.documents.get(document_id, for_update=for_update)
        if document is None:
            raise NotFoundError("document not found")
        return document


def _tax_context(company: Company, customer: Customer) -> TaxContext:
    return TaxContext(
        company_rules=profile_of(company.country).vat,
        company_small_business=company.small_business,
        customer_country=customer.address.country,
        customer_is_business=customer.is_business,
        customer_has_vat_number=customer.vat_number is not None,
        customer_tax_exempt=customer.tax_exempt,
        delivery_country=(
            None if customer.delivery_address is None else customer.delivery_address.country
        ),
    )


def _treatment(company: Company, customer: Customer) -> TaxTreatment:
    return determine_treatment(_tax_context(company, customer))


def _goods_treatment(
    treatment: TaxTreatment, company: Company, customer: Customer, *, overridden: bool
) -> TaxTreatment:
    return goods_treatment(treatment, _tax_context(company, customer), overridden=overridden)


def _with_treatments(content: DraftContent, company: Company, customer: Customer) -> DraftContent:
    """Determine the treatments again when issuing; a treatment chosen by hand stays."""
    overridden = content.treatment_overridden
    chosen = content.treatment if overridden else _treatment(company, customer)
    return replace(
        content,
        treatment=chosen,
        goods_treatment=_goods_treatment(chosen, company, customer, overridden=overridden),
    )


def _goods_notice(uow: UnitOfWork, content: DraftContent, company: Company) -> str | None:
    """Freeze the goods lines' notice only when they have a treatment of their own."""
    goods = content.goods_treatment
    if goods is None or goods not in content.treatments:
        return None
    return effective_notice(uow, goods, company.country, content.language)


def _invoice_texts(
    content: DraftContent, templates: list[TextTemplate], language: Language
) -> DraftContent:
    """Replace the quote's default texts with the invoice's; texts the user wrote stay."""

    def joined(document_type: DocumentType, kind: TextKind) -> str:
        return "\n".join(
            template.text
            for template in sorted(templates, key=lambda template: template.position)
            if (template.document_type, template.kind, template.language, template.is_default)
            == (document_type, kind, language, True)
        )

    def pick(current: str, kind: TextKind) -> str:
        if current == joined(DocumentType.QUOTE, kind):
            return joined(DocumentType.INVOICE, kind)
        return current

    return replace(
        content,
        intro_text=pick(content.intro_text, TextKind.INTRO),
        payment_text=pick(content.payment_text, TextKind.PAYMENT),
        closing_text=pick(content.closing_text, TextKind.CLOSING),
    )
