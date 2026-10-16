import logging
from datetime import date, datetime
from typing import Annotated, Any, Self
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, File, Query, UploadFile, status
from fastapi.responses import HTMLResponse, Response
from pydantic import Field

from rhinvoice.api.container import Container
from rhinvoice.api.dependencies import NOT_IN_DEMO, ContainerDep, CurrentUser
from rhinvoice.api.schemas import (
    DECIMAL_PATTERN,
    ERROR_RESPONSES,
    PERCENT_PATTERN,
    UNIT_CODES,
    AddressSchema,
    ApiModel,
    ListParams,
    plain_number,
    price_text,
    text,
)
from rhinvoice.application.common import SortDirection
from rhinvoice.application.document.bad_debts import BadDebtYear
from rhinvoice.application.document.dashboard import Dashboard
from rhinvoice.application.document.einvoice import EInvoiceProblem
from rhinvoice.application.document.handlers import (
    MAX_ADDED_FILE_BYTES,
    DocumentPreview,
    DocumentView,
    DraftInput,
    LineInput,
    PaymentInput,
    RecordedPayment,
    WriteOffInput,
)
from rhinvoice.application.document.ports import (
    DocumentFacets,
    DocumentQuery,
    DocumentSort,
    DocumentSummary,
)
from rhinvoice.domain.document.attachment import Attachment
from rhinvoice.domain.document.calculation import Totals
from rhinvoice.domain.document.document import (
    MAX_LINES,
    DisplayStatus,
    DocumentStatus,
    DocumentType,
    EventKind,
)
from rhinvoice.domain.document.lines import DiscountKind, LineKind, PriceMode
from rhinvoice.domain.document.write_off import WriteOffReason, tax_share
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency, Money
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply
from rhinvoice.domain.tax.treatment import TaxTreatment
from rhinvoice.domain.tax.vat_code import VatCode
from rhinvoice.infrastructure.rendering.pdf import pdf_file_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["documents"], responses=ERROR_RESPONSES)

QUANTITY_PATTERN = r"^-?\d{1,9}(\.\d{1,4})?$"
AMOUNT_PATTERN = r"^\d{1,10}(\.\d{1,2})?$"


def amount(value: Money) -> str:
    return f"{value.round_to_minor().amount:.2f}"


# --- Requests ---------------------------------------------------------------------------


class LineRequest(ApiModel):
    kind: LineKind = LineKind.ITEM
    description: str = text(500)
    details: str = text(4000)
    quantity: str = Field(default="1", pattern=QUANTITY_PATTERN)
    unit: str | None = Field(default=None, json_schema_extra={"enum": [*UNIT_CODES, None]})
    unit_price: str = Field(default="0", pattern=DECIMAL_PATTERN)
    discount_percent: str = Field(default="0", pattern=PERCENT_PATTERN)
    tax_category: TaxCategory = TaxCategory.STANDARD
    supply: Supply = Supply.SERVICE
    article_id: UUID | None = None

    def to_input(self) -> LineInput:
        return LineInput(
            kind=self.kind,
            description=self.description,
            details=self.details,
            quantity=self.quantity,
            unit=self.unit,
            unit_price=self.unit_price,
            discount_percent=self.discount_percent,
            tax_category=self.tax_category,
            supply=self.supply,
            article_id=self.article_id,
        )


class DraftRequest(ApiModel):
    customer_id: UUID
    currency: Currency | None = None
    language: Language | None = None
    price_mode: PriceMode = PriceMode.NET
    lines: list[LineRequest] = Field(default_factory=list[LineRequest], max_length=MAX_LINES)
    discount_kind: DiscountKind = DiscountKind.PERCENT
    discount_value: str | None = Field(default=None, pattern=DECIMAL_PATTERN)
    treatment_override: TaxTreatment | None = None
    override_reason: str = text(200)
    issue_date: date | None = None
    due_date: date | None = None
    service_from: date | None = None
    service_to: date | None = None
    subject: str = text(200)
    reference: str = text(100)
    intro_text: str = text(4000)
    payment_text: str = text(4000)
    closing_text: str = text(4000)

    def to_input(self) -> DraftInput:
        return DraftInput(
            customer_id=self.customer_id,
            currency=self.currency,
            language=self.language,
            price_mode=self.price_mode,
            lines=tuple(line.to_input() for line in self.lines),
            discount_kind=self.discount_kind,
            discount_value=self.discount_value,
            treatment_override=self.treatment_override,
            override_reason=self.override_reason,
            issue_date=self.issue_date,
            due_date=self.due_date,
            service_from=self.service_from,
            service_to=self.service_to,
            subject=self.subject,
            reference=self.reference,
            intro_text=self.intro_text,
            payment_text=self.payment_text,
            closing_text=self.closing_text,
        )


class CreateRequest(DraftRequest):
    type: DocumentType = Field(json_schema_extra={"enum": ["quote", "invoice"]})


class PaymentRequest(ApiModel):
    paid_on: date
    amount: str = Field(pattern=AMOUNT_PATTERN)
    note: str = text(500)


class MarkPaidRequest(ApiModel):
    paid_on: date


class WriteOffRequest(ApiModel):
    written_off_on: date
    """Not before the invoice date and not in the future."""
    reason: WriteOffReason
    note: str = text(500)


MAX_BULK = 100


class BulkMarkPaidRequest(ApiModel):
    document_ids: list[UUID] = Field(min_length=1, max_length=MAX_BULK)
    paid_on: date | None = None
    """None: today in the installation's time zone."""


class RecordedPaymentSchema(ApiModel):
    document_id: UUID
    payment_id: UUID


class RemovePaymentsRequest(ApiModel):
    payments: list[RecordedPaymentSchema] = Field(min_length=1, max_length=MAX_BULK)


# --- Responses ----------------------------------------------------------------------------


class LineResponse(ApiModel):
    id: UUID
    kind: LineKind
    description: str
    details: str
    quantity: str
    unit: str | None
    unit_price: str
    discount_percent: str
    tax_category: TaxCategory
    supply: Supply
    tax_rate: str | None
    """Frozen rate of issued documents; None for drafts."""
    amount: str | None
    """Line amount after the line discount (None for text lines)."""
    article_id: UUID | None


class TaxGroupResponse(ApiModel):
    vat_code: VatCode
    rate: str
    amount: str
    discount: str
    net: str
    tax: str


class TotalsResponse(ApiModel):
    currency: Currency
    subtotal: str
    discount: str
    net: str
    tax: str
    gross: str
    rounding: str
    total: str
    groups: list[TaxGroupResponse]

    @classmethod
    def of(cls, totals: Totals) -> Self:
        return cls(
            currency=totals.currency,
            subtotal=amount(totals.subtotal),
            discount=amount(totals.discount),
            net=amount(totals.net),
            tax=amount(totals.tax),
            gross=amount(totals.gross),
            rounding=amount(totals.rounding),
            total=amount(totals.total),
            groups=[
                TaxGroupResponse(
                    vat_code=group.vat_code,
                    rate=plain_number(group.rate),
                    amount=amount(group.amount),
                    discount=amount(group.discount),
                    net=amount(group.net),
                    tax=amount(group.tax),
                )
                for group in totals.groups
            ],
        )


class PaymentResponse(ApiModel):
    id: UUID
    paid_on: date
    amount: str
    note: str
    recorded_at: datetime
    after_write_off: bool
    """Came in after the invoice was written off."""


class WriteOffResponse(ApiModel):
    """What was open of the invoice when collecting it was given up."""

    id: UUID
    written_off_on: date
    amount: str
    tax: str
    """Tax contained in the amount; whether it is corrected depends on the accounting."""
    reason: WriteOffReason
    note: str
    recorded_at: datetime


class EventResponse(ApiModel):
    at: datetime
    kind: EventKind
    detail: str


class RecipientResponse(ApiModel):
    """The customer as printed: frozen for issued documents, current for drafts."""

    name: str
    contact_person: str
    address: AddressSchema
    vat_number: str | None


class DocumentResponse(ApiModel):
    id: UUID
    type: DocumentType
    status: DocumentStatus
    display_status: DisplayStatus
    number: str | None
    customer_id: UUID
    recipient: RecipientResponse | None
    currency: Currency
    language: Language
    price_mode: PriceMode
    treatment: TaxTreatment
    treatment_overridden: bool
    goods_treatment: TaxTreatment | None
    """Treatment of the goods lines (e.g. export delivery); None: the document's."""
    discount_kind: DiscountKind
    discount_value: str
    issue_date: date | None
    due_date: date | None
    service_from: date | None
    service_to: date | None
    subject: str
    reference: str
    intro_text: str
    payment_text: str
    closing_text: str
    notice: str
    """Legal notices of the treatments, one per line; frozen once issued."""
    lines: list[LineResponse]
    totals: TotalsResponse
    payments: list[PaymentResponse]
    paid_amount: str
    open_amount: str
    write_off: WriteOffResponse | None
    """Stays when the rest is paid after all (see ``written_off_amount``)."""
    written_off_amount: str
    """What is lost: the write-off less the payments that came in after it."""
    events: list[EventResponse]
    source_id: UUID | None
    cancelled_by_id: UUID | None
    converted_to_id: UUID | None
    created_at: datetime
    issued_at: datetime | None
    imported: bool
    """Issued by a program used before: its PDF is the invoice, it has no lines."""
    has_pdf: bool
    """The PDF is archived (always once printed; imported invoices may lack one)."""

    @classmethod
    def of(cls, view: DocumentView) -> Self:
        document = view.document
        content = document.content
        amounts = {line.line_id: line.amount for line in view.totals.lines}
        party = document.snapshot.customer if document.snapshot is not None else view.customer
        open_value = (
            document.open_amount() if document.issued_totals is not None else view.totals.total
        )
        write_off = document.write_off
        recoveries = {payment.id for payment in document.recoveries}
        return cls(
            id=document.id,
            type=document.type,
            status=document.status,
            display_status=view.display_status,
            number=document.number,
            customer_id=content.customer_id,
            recipient=(
                None
                if party is None
                else RecipientResponse(
                    name=party.display_name,
                    contact_person=party.contact_person,
                    address=AddressSchema.of(party.address),
                    vat_number=None if party.vat_number is None else str(party.vat_number),
                )
            ),
            currency=content.currency,
            language=content.language,
            price_mode=content.price_mode,
            treatment=content.treatment,
            treatment_overridden=content.treatment_overridden,
            goods_treatment=content.goods_treatment,
            discount_kind=content.discount.kind,
            discount_value=plain_number(content.discount.value),
            issue_date=content.issue_date,
            due_date=content.due_date,
            service_from=content.service_from,
            service_to=content.service_to,
            subject=content.subject,
            reference=content.reference,
            intro_text=content.intro_text,
            payment_text=content.payment_text,
            closing_text=content.closing_text,
            notice=view.notice,
            lines=[
                LineResponse(
                    id=line.id,
                    kind=line.kind,
                    description=line.description,
                    details=line.details,
                    quantity=plain_number(line.quantity),
                    unit=None if line.unit is None else line.unit.code,
                    unit_price=price_text(line.unit_price),
                    discount_percent=plain_number(line.discount_percent),
                    tax_category=line.tax_category,
                    supply=line.supply,
                    tax_rate=None if line.tax_rate is None else plain_number(line.tax_rate),
                    amount=amount(amounts[line.id]) if line.id in amounts else None,
                    article_id=line.article_id,
                )
                for line in content.lines
            ],
            totals=TotalsResponse.of(view.totals),
            payments=[
                PaymentResponse(
                    id=payment.id,
                    paid_on=payment.paid_on,
                    amount=amount(payment.amount),
                    note=payment.note,
                    recorded_at=payment.recorded_at,
                    after_write_off=payment.id in recoveries,
                )
                for payment in document.payments
            ],
            paid_amount=amount(document.paid_amount),
            open_amount=amount(open_value),
            write_off=(
                None
                if write_off is None
                else WriteOffResponse(
                    id=write_off.id,
                    written_off_on=write_off.written_off_on,
                    amount=amount(write_off.amount),
                    tax=amount(tax_share(write_off.amount, document.frozen_totals)),
                    reason=write_off.reason,
                    note=write_off.note,
                    recorded_at=write_off.recorded_at,
                )
            ),
            written_off_amount=amount(document.written_off_amount),
            events=[
                EventResponse(at=event.at, kind=event.kind, detail=event.detail)
                for event in document.events
            ],
            source_id=document.source_id,
            cancelled_by_id=document.cancelled_by_id,
            converted_to_id=document.converted_to_id,
            created_at=document.created_at,
            issued_at=document.issued_at,
            imported=document.is_imported,
            has_pdf=document.pdf_sha256 is not None,
        )


class AttachmentResponse(ApiModel):
    id: UUID
    file_name: str
    """With the folders it came from."""
    size: int
    sha256: str
    added_at: datetime

    @classmethod
    def of(cls, attachment: Attachment) -> Self:
        return cls(
            id=attachment.id,
            file_name=attachment.file_name,
            size=attachment.size,
            sha256=attachment.sha256,
            added_at=attachment.added_at,
        )


class DocumentPreviewResponse(ApiModel):
    """Totals of an unsaved draft."""

    treatment: TaxTreatment
    goods_treatment: TaxTreatment | None
    """Treatment of the goods lines (e.g. export delivery); None: the document's."""
    line_amounts: list[str | None]
    """Amount of each line after its discount, in input order (None for text lines)."""
    totals: TotalsResponse
    rates: dict[TaxCategory, str]
    """Rate per tax category for this draft (0 when the treatment charges no VAT)."""
    notice: str
    """Legal notice the treatment puts on the document."""
    customer_vat_missing: bool
    """The customer is an EU business without a VAT number: with one, reverse charge."""
    e_invoice_problems: list[EInvoiceProblem]
    """What keeps the invoice, issued now, from carrying its e-invoice (ZUGFeRD)."""
    xrechnung_problems: list[EInvoiceProblem]
    """What the invoice, issued now, would lack as XRechnung; German customers only."""

    @classmethod
    def of(
        cls,
        preview: DocumentPreview,
        e_invoice_problems: tuple[EInvoiceProblem, ...],
        xrechnung_problems: tuple[EInvoiceProblem, ...],
    ) -> Self:
        view = preview.view
        amounts = {line.line_id: line.amount for line in view.totals.lines}
        return cls(
            customer_vat_missing=preview.customer_vat_missing,
            e_invoice_problems=list(e_invoice_problems),
            xrechnung_problems=list(xrechnung_problems),
            rates={category: plain_number(rate) for category, rate in preview.rates.items()},
            treatment=view.document.content.treatment,
            goods_treatment=view.document.content.goods_treatment,
            line_amounts=[
                amount(amounts[line.id]) if line.id in amounts else None
                for line in view.document.content.lines
            ],
            totals=TotalsResponse.of(view.totals),
            notice=view.notice,
        )


class SummaryResponse(ApiModel):
    id: UUID
    type: DocumentType
    status: DocumentStatus
    display_status: DisplayStatus
    number: str | None
    customer_id: UUID
    customer_name: str
    subject: str
    issue_date: date | None
    due_date: date | None
    currency: Currency
    total: str
    open_amount: str
    created_at: datetime
    imported: bool

    @classmethod
    def of(cls, summary: DocumentSummary) -> Self:
        return cls(
            id=summary.id,
            type=summary.type,
            status=summary.status,
            display_status=summary.display_status,
            number=summary.number,
            customer_id=summary.customer_id,
            customer_name=summary.customer_name,
            subject=summary.subject,
            issue_date=summary.issue_date,
            due_date=summary.due_date,
            currency=summary.currency,
            total=amount(summary.total),
            open_amount=amount(summary.open_amount),
            created_at=summary.created_at,
            imported=summary.imported,
        )


class CurrencyTotalsResponse(ApiModel):
    currency: Currency
    count: int
    total: str
    open: str


class StatusCountResponse(ApiModel):
    status: DisplayStatus
    count: int


class DocumentPage(ApiModel):
    items: list[SummaryResponse]
    total: int
    totals: list[CurrencyTotalsResponse]
    """Sums of the issued, not cancelled documents of the whole selection, per currency."""
    status_counts: list[StatusCountResponse]
    """Documents per status of the selection without the status filter (no cancellations)."""
    years: list[int]
    """Years with documents of the selected types, newest first."""

    @classmethod
    def of(cls, items: list[SummaryResponse], total: int, facets: DocumentFacets) -> Self:
        return cls(
            items=items,
            total=total,
            totals=[
                CurrencyTotalsResponse(
                    currency=item.currency,
                    count=item.count,
                    total=amount(item.total),
                    open=amount(item.open),
                )
                for item in facets.totals
            ],
            status_counts=[
                StatusCountResponse(status=status, count=count)
                for status, count in sorted(facets.status_counts.items())
            ],
            years=facets.years,
        )


class BadDebtYearResponse(ApiModel):
    year: int
    currency: Currency
    written_off: str
    """Written off with a date in the year."""
    recovered: str
    """Paid in the year on invoices written off before."""
    loss: str
    """Written off less recovered."""
    net: str
    tax: str
    """Tax contained in the loss."""

    @classmethod
    def of(cls, year: BadDebtYear) -> Self:
        return cls(
            year=year.year,
            currency=year.currency,
            written_off=amount(year.written_off),
            recovered=amount(year.recovered),
            loss=amount(year.loss),
            net=amount(year.net),
            tax=amount(year.tax),
        )


class BulkPaymentsResponse(ApiModel):
    payments: list[RecordedPaymentSchema]


class DocumentSearch(ListParams):
    direction: SortDirection = SortDirection.DESC
    type: list[DocumentType] = Field(default_factory=lambda: list(DocumentType), max_length=3)
    status: list[DisplayStatus] = Field(
        default_factory=list[DisplayStatus], max_length=len(DisplayStatus)
    )
    customer_id: UUID | None = None
    year: int | None = Field(default=None, ge=1900, le=9999)
    sort: DocumentSort = DocumentSort.CREATED_AT


class FiguresResponse(ApiModel):
    currency: Currency
    open: str
    overdue: str
    paid: str
    open_count: int
    overdue_count: int


class RevenueResponse(ApiModel):
    month: date
    currency: Currency
    net: str


class ActivityResponse(ApiModel):
    document: SummaryResponse
    event: EventKind
    at: datetime


class AgingResponse(ApiModel):
    currency: Currency
    not_due: str
    late_30: str
    """1-30 days overdue."""
    late_60: str
    """31-60 days overdue."""
    late_more: str
    """More than 60 days overdue."""


class ExpectedWeekResponse(ApiModel):
    currency: Currency
    week_start: date
    """Monday; the first week includes everything overdue."""
    amount: str


class QuoteFiguresResponse(ApiModel):
    currency: Currency
    open: str
    open_count: int
    accepted: int
    """Accepted quotes of this year ..."""
    decided: int
    """... of all decided ones (accepted, declined, expired)."""


class CustomerRevenueResponse(ApiModel):
    customer_id: UUID
    customer_name: str
    currency: Currency
    net: str


class YearToDateResponse(ApiModel):
    currency: Currency
    current: str
    """Net revenue from 1 January to today."""
    previous: str
    """Last year up to the same day."""


class DaysToPayResponse(ApiModel):
    currency: Currency
    days: int
    """Average days from issuing to the last payment over the last year."""


class DashboardResponse(ApiModel):
    today: date
    """In the installation's time zone."""
    currency: Currency | None
    """The company's default currency, shown first; null before the company is set up."""
    figures: list[FiguresResponse]
    revenue: list[RevenueResponse]
    """Per month since January of last year."""
    year_to_date: list[YearToDateResponse]
    recent: list[ActivityResponse]
    aging: list[AgingResponse]
    expected: list[ExpectedWeekResponse]
    overdue: list[SummaryResponse]
    """The longest overdue invoices first, at most five per currency."""
    quotes: list[QuoteFiguresResponse]
    top_customers: list[CustomerRevenueResponse]
    """This year's best customers, per currency."""
    days_to_pay: list[DaysToPayResponse]

    @classmethod
    def of(cls, dashboard: Dashboard) -> Self:
        return cls(
            figures=[
                FiguresResponse(
                    currency=figure.currency,
                    open=amount(figure.open),
                    overdue=amount(figure.overdue),
                    paid=amount(figure.paid),
                    open_count=figure.open_count,
                    overdue_count=figure.overdue_count,
                )
                for figure in dashboard.figures
            ],
            revenue=[
                RevenueResponse(month=item.month, currency=item.currency, net=amount(item.net))
                for item in dashboard.revenue
            ],
            recent=[
                ActivityResponse(document=SummaryResponse.of(summary), event=EventKind(kind), at=at)
                for summary, kind, at in dashboard.recent
            ],
            aging=[
                AgingResponse(
                    currency=item.currency,
                    not_due=amount(item.not_due),
                    late_30=amount(item.late_30),
                    late_60=amount(item.late_60),
                    late_more=amount(item.late_more),
                )
                for item in dashboard.aging
            ],
            expected=[
                ExpectedWeekResponse(
                    currency=week.currency, week_start=week.week_start, amount=amount(week.amount)
                )
                for week in dashboard.expected
            ],
            overdue=[SummaryResponse.of(summary) for summary in dashboard.overdue],
            quotes=[
                QuoteFiguresResponse(
                    currency=item.currency,
                    open=amount(item.open),
                    open_count=item.open_count,
                    accepted=item.accepted,
                    decided=item.decided,
                )
                for item in dashboard.quotes
            ],
            top_customers=[
                CustomerRevenueResponse(
                    customer_id=entry.customer_id,
                    customer_name=entry.customer_name,
                    currency=entry.currency,
                    net=amount(entry.net),
                )
                for entry in dashboard.top_customers
            ],
            days_to_pay=[
                DaysToPayResponse(currency=item.currency, days=item.days)
                for item in dashboard.days_to_pay
            ],
            today=dashboard.today,
            currency=dashboard.currency,
            year_to_date=[
                YearToDateResponse(
                    currency=item.currency,
                    current=amount(item.current),
                    previous=amount(item.previous),
                )
                for item in dashboard.year_to_date
            ],
        )


# --- Routes -------------------------------------------------------------------------------


@router.get("/documents")
def search_documents(
    params: Annotated[DocumentSearch, Query()],
    _user: CurrentUser,
    container: ContainerDep,
) -> DocumentPage:
    query = DocumentQuery(
        today=container.clock.today(),
        types=frozenset(params.type),
        statuses=frozenset(params.status),
        customer_id=params.customer_id,
        year=params.year,
        zone=container.settings.zone,
        search=params.q,
        sort=params.sort,
        direction=params.direction,
        page=params.page_request(),
    )
    page = container.documents.search(query)
    return DocumentPage.of(
        [SummaryResponse.of(item) for item in page.items],
        page.total,
        container.documents.facets(query),
    )


@router.post("/documents", status_code=status.HTTP_201_CREATED)
def create_document(
    body: CreateRequest, _user: CurrentUser, container: ContainerDep
) -> DocumentResponse:
    return DocumentResponse.of(container.documents.create(body.type, body.to_input()))


@router.post("/documents/preview")
def preview_document(
    body: CreateRequest, _user: CurrentUser, container: ContainerDep
) -> DocumentPreviewResponse:
    """Calculate the totals of a draft without saving it."""
    preview = container.documents.preview(body.type, body.to_input())
    printing = container.printing
    return DocumentPreviewResponse.of(
        preview,
        printing.draft_e_invoice_problems(preview.view),
        printing.draft_xrechnung_problems(preview.view),
    )


HTML_PAGE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The document as an HTML page (A4)",
        "content": {"text/html": {"schema": {"type": "string"}}},
    },
    # Errors stay JSON; without this they would be documented as text/html.
    **{
        status: {
            "description": description,
            "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}},
            },
        }
        for status, description in (
            (400, "Bad Request"),
            (401, "Unauthorized"),
            (403, "Forbidden"),
            (404, "Not Found"),
            (409, "Conflict"),
            (422, "Unprocessable Content"),
        )
    },
}


@router.post("/documents/render", response_class=HTMLResponse, responses=HTML_PAGE)
def render_draft(body: CreateRequest, _user: CurrentUser, container: ContainerDep) -> HTMLResponse:
    """Render a draft as a page without saving it (live preview in the editor)."""
    return HTMLResponse(container.printing.preview_html(body.type, body.to_input()))


@router.get("/documents/{document_id}/html", response_class=HTMLResponse, responses=HTML_PAGE)
def render_document(document_id: UUID, _user: CurrentUser, container: ContainerDep) -> HTMLResponse:
    """Render the document as the customer sees it (same template as the PDF)."""
    return HTMLResponse(container.printing.html(document_id))


PDF_FILE: dict[int | str, dict[str, Any]] = {
    **HTML_PAGE,
    200: {
        "description": "The document as PDF; issued documents always return the archived file",
        "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
    },
    503: {
        "description": "No PDF service configured or reachable",
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}},
        },
    },
}


@router.get("/documents/{document_id}/pdf", response_class=Response, responses=PDF_FILE)
def document_pdf(
    document_id: UUID,
    _user: CurrentUser,
    container: ContainerDep,
    download: bool = False,  # noqa: FBT001, FBT002 - a query flag
) -> Response:
    """Return the PDF, shown in the browser or (``download``) saved as a file."""
    file = container.printing.pdf(document_id)
    name = pdf_file_name(file.document)
    # filename*: the full UTF-8 name; filename: an ASCII fallback for old clients.
    fallback = name.encode("ascii", "replace").decode().replace("?", "_")
    disposition = "attachment" if download else "inline"
    headers = {
        "Content-Disposition": (
            f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}"
        ),
        # Drafts change, issued documents never do.
        "Cache-Control": "no-store" if file.sha256 is None else "private, max-age=31536000",
    }
    if file.sha256 is not None:
        headers["ETag"] = f'"{file.sha256}"'
    return Response(content=file.content, media_type="application/pdf", headers=headers)


@router.get("/documents/{document_id}/attachments")
def list_attachments(
    document_id: UUID, _user: CurrentUser, container: ContainerDep
) -> list[AttachmentResponse]:
    """Further files of an imported invoice: reminders, corrected copies, versions."""
    return [AttachmentResponse.of(item) for item in container.documents.attachments(document_id)]


ATTACHMENT_FILE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The file as it was added",
        "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
    },
}


@router.get(
    "/documents/{document_id}/attachments/{attachment_id}",
    response_class=Response,
    responses=ATTACHMENT_FILE,
)
def attachment_file(
    document_id: UUID,
    attachment_id: UUID,
    _user: CurrentUser,
    container: ContainerDep,
    download: bool = False,  # noqa: FBT001, FBT002 - a query flag
) -> Response:
    """Return an attachment, shown in the browser or (``download``) saved as a file."""
    attachment, content = container.documents.attachment(document_id, attachment_id)
    name = attachment.file_name.rsplit("/", 1)[-1]
    fallback = name.encode("ascii", "replace").decode().replace("?", "_").replace('"', "_")
    disposition = "attachment" if download else "inline"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}"
            ),
            "Cache-Control": "private, max-age=31536000",
            "ETag": f'"{attachment.sha256}"',
        },
    )


@router.post("/documents/{document_id}/files", dependencies=[NOT_IN_DEMO])
def add_file(
    document_id: UUID,
    file: Annotated[UploadFile, File(description="A PDF, at most 20 MB")],
    _user: CurrentUser,
    container: ContainerDep,
) -> DocumentResponse:
    """Add a PDF to an imported invoice: its original if it has none, else an attachment.

    Neither can be replaced or removed afterwards.
    """
    # Synchronous on purpose (thread pool); one byte more lets the handler refuse large files.
    content = file.file.read(MAX_ADDED_FILE_BYTES + 1)
    name = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1] or "document.pdf"
    return DocumentResponse.of(container.documents.add_file(document_id, name, content))


@router.get("/documents/{document_id}")
def get_document(
    document_id: UUID, _user: CurrentUser, container: ContainerDep
) -> DocumentResponse:
    return DocumentResponse.of(container.documents.get(document_id))


@router.put("/documents/{document_id}")
def update_document(
    document_id: UUID,
    body: DraftRequest,
    _user: CurrentUser,
    container: ContainerDep,
) -> DocumentResponse:
    """Replace the content of a draft (all fields and lines at once)."""
    return DocumentResponse.of(container.documents.update(document_id, body.to_input()))


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: UUID, _user: CurrentUser, container: ContainerDep) -> None:
    """Delete a draft. Issued documents are never deleted (409)."""
    container.documents.delete(document_id)


@router.post("/documents/{document_id}/issue")
def issue_document(
    document_id: UUID, _user: CurrentUser, container: ContainerDep
) -> DocumentResponse:
    """Assign the number and freeze the document (quotes become "sent")."""
    view = container.documents.issue(document_id)
    _archive(container, document_id)
    return DocumentResponse.of(view)


def _archive(container: Container, document_id: UUID) -> None:
    """Freeze the PDF right after issuing, so later template or logo changes do not affect it."""
    if not container.printing.archive(document_id):
        logger.warning("PDF of document %s not archived yet: no PDF service", document_id)


@router.post("/documents/{document_id}/accept")
def accept_quote(
    document_id: UUID, _user: CurrentUser, container: ContainerDep
) -> DocumentResponse:
    return DocumentResponse.of(container.documents.accept(document_id))


@router.post("/documents/{document_id}/decline")
def decline_quote(
    document_id: UUID, _user: CurrentUser, container: ContainerDep
) -> DocumentResponse:
    return DocumentResponse.of(container.documents.decline(document_id))


@router.post("/documents/{document_id}/convert", status_code=status.HTTP_201_CREATED)
def convert_quote(
    document_id: UUID, _user: CurrentUser, container: ContainerDep
) -> DocumentResponse:
    """Create an invoice draft from a quote."""
    return DocumentResponse.of(container.documents.convert_to_invoice(document_id))


@router.post("/documents/{document_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_document(
    document_id: UUID, _user: CurrentUser, container: ContainerDep
) -> DocumentResponse:
    return DocumentResponse.of(container.documents.duplicate(document_id))


@router.post("/documents/{document_id}/cancel")
def cancel_invoice(
    document_id: UUID, _user: CurrentUser, container: ContainerDep
) -> DocumentResponse:
    """Issue a cancellation invoice (Storno) and return the cancelled invoice."""
    view = container.documents.cancel(document_id)
    _archive(container, view.document.cancellation_id)
    return DocumentResponse.of(view)


@router.post("/documents/{document_id}/payments")
def add_payment(
    document_id: UUID,
    body: PaymentRequest,
    _user: CurrentUser,
    container: ContainerDep,
) -> DocumentResponse:
    return DocumentResponse.of(
        container.documents.add_payment(
            document_id,
            PaymentInput(paid_on=body.paid_on, amount=body.amount, note=body.note),
        ),
    )


@router.post("/documents/{document_id}/mark-paid")
def mark_paid(
    document_id: UUID,
    body: MarkPaidRequest,
    _user: CurrentUser,
    container: ContainerDep,
) -> DocumentResponse:
    """Record a payment of the whole open amount."""
    return DocumentResponse.of(container.documents.mark_paid(document_id, body.paid_on))


@router.post("/documents/mark-paid")
def mark_paid_many(
    body: BulkMarkPaidRequest,
    _user: CurrentUser,
    container: ContainerDep,
) -> BulkPaymentsResponse:
    """Pay several invoices in full at once; if one cannot be paid, none is (409)."""
    recorded = container.documents.mark_paid_many(body.document_ids, body.paid_on)
    return BulkPaymentsResponse(
        payments=[
            RecordedPaymentSchema(document_id=item.document_id, payment_id=item.payment_id)
            for item in recorded
        ],
    )


@router.post("/documents/remove-payments", status_code=status.HTTP_204_NO_CONTENT)
def remove_payments(
    body: RemovePaymentsRequest,
    _user: CurrentUser,
    container: ContainerDep,
) -> None:
    """Remove several payments at once, e.g. to undo a bulk "paid"; all of them or none."""
    container.documents.remove_payments(
        [
            RecordedPayment(document_id=item.document_id, payment_id=item.payment_id)
            for item in body.payments
        ],
    )


@router.delete("/documents/{document_id}/payments/{payment_id}")
def remove_payment(
    document_id: UUID,
    payment_id: UUID,
    _user: CurrentUser,
    container: ContainerDep,
) -> DocumentResponse:
    return DocumentResponse.of(container.documents.remove_payment(document_id, payment_id))


@router.post("/documents/{document_id}/write-off")
def write_off_invoice(
    document_id: UUID,
    body: WriteOffRequest,
    _user: CurrentUser,
    container: ContainerDep,
) -> DocumentResponse:
    """Give up collecting the open rest. The invoice stays as issued; nothing is sent."""
    return DocumentResponse.of(
        container.documents.write_off(
            document_id,
            WriteOffInput(written_off_on=body.written_off_on, reason=body.reason, note=body.note),
        ),
    )


@router.delete("/documents/{document_id}/write-off")
def remove_write_off(
    document_id: UUID, _user: CurrentUser, container: ContainerDep
) -> DocumentResponse:
    """Take a write-off back: the rest of the invoice is open again."""
    return DocumentResponse.of(container.documents.remove_write_off(document_id))


@router.get("/bad-debts")
def bad_debts(_user: CurrentUser, container: ContainerDep) -> list[BadDebtYearResponse]:
    """Written-off amounts per year and currency, the latest year first."""
    return [BadDebtYearResponse.of(year) for year in container.documents.bad_debts()]


@router.get("/dashboard")
def dashboard(_user: CurrentUser, container: ContainerDep) -> DashboardResponse:
    return DashboardResponse.of(container.dashboard.overview())
