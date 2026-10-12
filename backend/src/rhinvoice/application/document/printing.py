"""Documents as the customer sees them: the data the print template needs.

The same template renders the live preview in the editor, the document view
and the PDF, so all three look identical.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Protocol

from rhinvoice.application.common import PageRequest
from rhinvoice.application.customer.ports import CustomerQuery
from rhinvoice.application.document.einvoice import (
    EInvoiceProblem,
    EInvoiceProfile,
    EInvoiceWriter,
    is_e_invoice,
    is_e_invoice_type,
    problems,
)
from rhinvoice.application.document.handlers import DraftInput, LineInput
from rhinvoice.application.document.ports import DocumentQuery
from rhinvoice.application.errors import ConflictError, NotFoundError, UnavailableError
from rhinvoice.domain.company.print_layout import PrintLayout
from rhinvoice.domain.document.document import DocumentType, default_due_date
from rhinvoice.domain.document.lines import LineKind

if TYPE_CHECKING:
    from datetime import date
    from uuid import UUID

    from rhinvoice.application.document.handlers import DocumentHandlers, DocumentView
    from rhinvoice.application.uow import UnitOfWorkFactory
    from rhinvoice.domain.company.bank_account import BankAccount
    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.company.logo import Logo
    from rhinvoice.domain.customer.customer import Customer
    from rhinvoice.domain.document.document import Document
    from rhinvoice.domain.dunning.reminder import Reminder
    from rhinvoice.domain.shared.clock import Clock
    from rhinvoice.domain.shared.money import Money


_ONE = PageRequest(limit=1)
_INVOICES = frozenset({DocumentType.INVOICE})
SAMPLE_LINE = LineInput(kind=LineKind.ITEM, description="Beratung", quantity="2", unit_price="150")
"""The position of the sample invoice when there is none to show the layout with."""


@dataclass(frozen=True, slots=True)
class PrintModel:
    view: DocumentView
    company: Company
    """As issued (snapshot), the current one for drafts."""
    recipient: Customer | None
    """As issued (snapshot), the current customer for drafts."""
    bank_account: BankAccount | None
    """The account to pay to: as issued, the default of the currency for drafts."""
    logo: Logo | None
    issue_date: date
    """The document date; for drafts without a date the day it would be issued."""
    due_date: date | None
    """Due date of invoices, validity of quotes; derived for drafts without one."""
    cancelled_number: str | None = None
    """Number of the invoice a cancellation cancels."""
    cancelled_issue_date: date | None = None
    """Date of the invoice a cancellation cancels."""
    layout: PrintLayout = field(default_factory=PrintLayout)
    accounts: tuple[BankAccount, ...] = ()
    """Every bank account, for footers that list all of them."""
    amount_due: Money | None = None
    """What the payment codes ask for when it is not the total (reminders add a fee)."""
    cancelled_account: BankAccount | None = None
    """The account of the invoice a cancellation cancels; not printed, but XRechnung
    asks credit notes for payment instructions too (BR-DE-1)."""

    @property
    def payable(self) -> Money:
        return self.view.totals.total if self.amount_due is None else self.amount_due

    @property
    def is_draft(self) -> bool:
        return self.view.document.is_draft


@dataclass(frozen=True, slots=True)
class ReminderPrint:
    """A payment reminder on paper: the invoice's page with the reminder's content."""

    model: PrintModel
    """The invoice; its payment codes ask for the reminder's total."""
    reminder: Reminder
    text: str
    """The level's text in the invoice's language ({faellig} etc. still to fill in)."""


class DocumentRenderer(Protocol):
    def html(self, model: PrintModel) -> str:
        """Render the document as a complete HTML page (A4)."""
        ...

    def reminder_html(self, reminder: ReminderPrint) -> str:
        """Render a payment reminder as a complete HTML page (A4)."""
        ...


class PdfRenderer(Protocol):
    def pdf(self, model: PrintModel, e_invoice: bytes | None = None) -> bytes:
        """Render the document as a PDF/A that looks exactly like the HTML page.

        An e-invoice (CII XML) is embedded as ZUGFeRD / Factur-X.
        """
        ...

    def reminder_pdf(self, reminder: ReminderPrint) -> bytes:
        """Render a payment reminder as a PDF."""
        ...


@dataclass(frozen=True, slots=True)
class PdfFile:
    content: bytes
    document: Document
    """The document as printed (for the file name)."""
    sha256: str | None
    """The archived hash of issued documents, None for drafts."""


@dataclass(frozen=True, slots=True)
class EInvoiceStatus:
    """Whether an invoice is (or will be) an e-invoice, and what keeps it from one."""

    enabled: bool
    """The print layout embeds e-invoices."""
    embedded: bool | None
    """Whether the archived PDF holds the e-invoice; None while no PDF is archived."""
    problems: dict[EInvoiceProfile, tuple[EInvoiceProblem, ...]]


@dataclass(frozen=True, slots=True)
class PrintHandlers:
    uow: UnitOfWorkFactory
    clock: Clock
    documents: DocumentHandlers
    renderer: DocumentRenderer
    pdf_renderer: PdfRenderer | None = None
    """None when no PDF service (Gotenberg) is configured."""
    e_invoices: EInvoiceWriter | None = None
    """None: PDFs without e-invoice, no XRechnung."""

    def html(self, document_id: UUID) -> str:
        return self.renderer.html(self.model(self.documents.get(document_id)))

    def preview_html(self, document_type: DocumentType, draft: DraftInput) -> str:
        """Render a draft without saving it, for the live preview in the editor."""
        return self.renderer.html(self.model(self.documents.preview(document_type, draft).view))

    def layout_preview_html(self, layout: PrintLayout) -> str:
        """Render the latest invoice with a layout that is not saved yet.

        Without invoices a sample invoice to the first customer is shown.
        """
        with self.uow() as uow:
            invoices = uow.documents.search(
                DocumentQuery(today=self.clock.today(), types=_INVOICES, page=_ONE)
            ).items
            customers = uow.customers.search(CustomerQuery(page=_ONE)).items
        if invoices:
            view = self.documents.get(invoices[0].id)
        elif customers:
            draft = DraftInput(customer_id=customers[0].id, lines=(SAMPLE_LINE,))
            view = self.documents.preview(DocumentType.INVOICE, draft).view
        else:
            raise ConflictError(
                "the preview needs an invoice or a customer", code="preview_needs_customer"
            )
        return self.renderer.html(replace(self.model(view), layout=layout))

    def reminder(self, reminder_id: UUID) -> ReminderPrint:
        with self.uow() as uow:
            reminder = uow.dunning.get(reminder_id)
        if reminder is None:
            raise NotFoundError("reminder not found")
        model = self.model(self.documents.get(reminder.invoice_id))
        return ReminderPrint(
            model=replace(model, amount_due=reminder.total), reminder=reminder, text=reminder.text
        )

    def reminder_html(self, reminder_id: UUID) -> str:
        return self.renderer.reminder_html(self.reminder(reminder_id))

    def reminder_pdf(self, reminder_id: UUID) -> tuple[ReminderPrint, bytes]:
        """Render a reminder as PDF; reminders are not archived (the invoice is)."""
        if self.pdf_renderer is None:
            raise UnavailableError("PDFs need the Gotenberg service (RHINVOICE_GOTENBERG_URL)")
        printed = self.reminder(reminder_id)
        return printed, self.pdf_renderer.reminder_pdf(printed)

    def pdf(self, document_id: UUID) -> PdfFile:
        """Return the PDF of a document; issued documents keep the first one forever.

        Archiving on the first request (instead of while issuing) keeps issuing
        independent of the PDF service; the content is frozen either way.
        """
        view = self.documents.get(document_id)
        document = view.document
        if document.is_draft:
            content, _ = self._render(view)
            return PdfFile(content=content, document=document, sha256=None)
        with self.uow() as uow:
            stored = uow.documents.get_pdf(document_id)
        if stored is not None:
            return PdfFile(content=stored, document=document, sha256=document.pdf_sha256)
        content, e_invoice = self._render(view)
        with self.uow() as uow:
            locked = uow.documents.get(document_id, for_update=True)
            if locked is None:
                raise NotFoundError("document not found")
            stored = uow.documents.get_pdf(document_id)
            if stored is not None:
                # Archived by a concurrent request meanwhile: that one counts.
                return PdfFile(content=stored, document=locked, sha256=locked.pdf_sha256)
            archived = locked.archive_pdf(hashlib.sha256(content).hexdigest())
            uow.documents.archive_pdf(archived, content, e_invoice)
            uow.commit()
        return PdfFile(content=content, document=archived, sha256=archived.pdf_sha256)

    def archive(self, document_id: UUID) -> bool:
        """Archive the PDF of a just issued document right away.

        Returns False when the PDF service is unavailable; the PDF is then
        archived on the first download instead.
        """
        try:
            self.pdf(document_id)
        except UnavailableError:
            return False
        return True

    def _render(self, view: DocumentView) -> tuple[bytes, bytes | None]:
        """Render the PDF and return it with the e-invoice it embeds."""
        if self.pdf_renderer is None:
            raise UnavailableError("PDFs need the Gotenberg service (RHINVOICE_GOTENBERG_URL)")
        model = self.model(view)
        e_invoice = self._embedded_e_invoice(model)
        return self.pdf_renderer.pdf(model, e_invoice), e_invoice

    def _embedded_e_invoice(self, model: PrintModel) -> bytes | None:
        """Write the ZUGFeRD XML of an issued invoice, when enabled and complete."""
        writer = self.e_invoices
        if (
            writer is None
            or not model.layout.e_invoice
            or not is_e_invoice(model.view.document)
            or problems(model, EInvoiceProfile.EN16931)
        ):
            return None
        return writer.xml(model, EInvoiceProfile.EN16931)

    def draft_e_invoice_problems(self, view: DocumentView) -> tuple[EInvoiceProblem, ...]:
        """Name what an invoice draft, issued now, would lack for its e-invoice.

        Nothing for quotes, when e-invoices are switched off, or before a customer is chosen.
        """
        if self.e_invoices is None or view.customer is None or not is_e_invoice_type(view.document):
            return ()
        model = self.model(view)
        if not model.layout.e_invoice:
            return ()
        return problems(model, EInvoiceProfile.EN16931)

    def e_invoice_status(self, document_id: UUID) -> EInvoiceStatus:
        """Tell an invoice's e-invoice; for drafts what it will be when issued now."""
        if self.e_invoices is None:
            raise UnavailableError("e-invoices are not configured")
        view = self.documents.get(document_id)
        if not is_e_invoice_type(view.document):
            raise ConflictError("quotes are no e-invoices", code="not_an_e_invoice")
        model = self.model(view)
        embedded = None
        if view.document.pdf_sha256 is not None:
            with self.uow() as uow:
                embedded = uow.documents.get_e_invoice(document_id) is not None
        return EInvoiceStatus(
            enabled=model.layout.e_invoice,
            embedded=embedded,
            problems={profile: problems(model, profile) for profile in EInvoiceProfile},
        )

    def xrechnung(self, document_id: UUID) -> tuple[Document, bytes]:
        """Write an issued invoice as XRechnung (CII), for German authorities."""
        writer = self.e_invoices
        if writer is None:
            raise UnavailableError("e-invoices are not configured")
        view = self.documents.get(document_id)
        if not is_e_invoice(view.document):
            raise ConflictError(
                "only issued invoices and cancellations are e-invoices", code="not_an_e_invoice"
            )
        model = self.model(view)
        missing_details = problems(model, EInvoiceProfile.XRECHNUNG)
        if missing_details:
            missing = ", ".join(problem.value for problem in missing_details)
            raise ConflictError(
                f"the invoice is no complete XRechnung: {missing}", code="e_invoice_incomplete"
            )
        return model.view.document, writer.xml(model, EInvoiceProfile.XRECHNUNG)

    def model(self, view: DocumentView) -> PrintModel:
        document = view.document
        content = document.content
        with self.uow() as uow:
            logo = uow.company.get_logo()
            layout = uow.company.print_layout()
            accounts = tuple(uow.bank_accounts.list())
            if not document.is_draft:
                snapshot = document.issued_snapshot
                source = (
                    None
                    if document.type is not DocumentType.CANCELLATION or document.source_id is None
                    else uow.documents.get(document.source_id)
                )
                return PrintModel(
                    view=view,
                    company=snapshot.company,
                    recipient=snapshot.customer,
                    bank_account=snapshot.bank_account,
                    logo=logo,
                    issue_date=content.issue_date or self.clock.today(),
                    due_date=content.due_date,
                    cancelled_number=None if source is None else source.number,
                    cancelled_issue_date=None if source is None else source.content.issue_date,
                    cancelled_account=(
                        None if source is None else source.issued_snapshot.bank_account
                    ),
                    # As on the day of issuing; older documents take today's.
                    layout=layout if snapshot.layout is None else snapshot.layout,
                    accounts=accounts if snapshot.accounts is None else snapshot.accounts,
                )
            company = view.company
            account = next(
                (
                    account
                    for account in accounts
                    if account.currency is content.currency and account.is_default
                ),
                None,
            )
        issue_date = content.issue_date or self.clock.today()
        terms = None if view.customer is None else view.customer.payment_terms_days
        due_date = content.due_date or default_due_date(
            document.type, issue_date, company.payment_terms_days if terms is None else terms
        )
        return PrintModel(
            view=view,
            company=company,
            recipient=view.customer,
            bank_account=account,
            logo=logo,
            issue_date=issue_date,
            due_date=due_date,
            layout=layout,
            accounts=accounts,
        )
