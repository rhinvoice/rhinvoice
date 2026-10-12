from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from rhinvoice.application.common import PageRequest, SortDirection
from rhinvoice.domain.shared.clock import DEFAULT_TIMEZONE

if TYPE_CHECKING:
    from datetime import date, datetime
    from uuid import UUID
    from zoneinfo import ZoneInfo

    from rhinvoice.application.common import Page
    from rhinvoice.domain.document.document import (
        DisplayStatus,
        Document,
        DocumentStatus,
        DocumentType,
    )
    from rhinvoice.domain.shared.money import Currency, Money


@dataclass(frozen=True, slots=True)
class DocumentIndex:
    """Denormalised values for lists, sorting, full-text search and the dashboard."""

    customer_name: str
    net: Money
    total: Money
    open_amount: Money
    search_text: str


class DocumentSort(StrEnum):
    NUMBER = "number"
    ISSUE_DATE = "issue_date"
    DUE_DATE = "due_date"
    CUSTOMER = "customer"
    TOTAL = "total"
    CREATED_AT = "created_at"


@dataclass(frozen=True, slots=True)
class DocumentQuery:
    today: date
    types: frozenset[DocumentType]
    statuses: frozenset[DisplayStatus] = frozenset()
    """Empty: all statuses. "overdue" and "expired" are derived from the due date."""
    customer_id: UUID | None = None
    year: int | None = None
    """Calendar year of the issue date (drafts: of the creation date)."""
    zone: ZoneInfo = DEFAULT_TIMEZONE
    """Time zone of the installation: the creation date of drafts is the local date."""
    search: str = ""
    sort: DocumentSort = DocumentSort.CREATED_AT
    direction: SortDirection = SortDirection.DESC
    page: PageRequest = field(default_factory=PageRequest)


@dataclass(frozen=True, slots=True)
class DocumentSummary:
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
    total: Money
    open_amount: Money
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CurrencyTotals:
    """Sums of the issued, not cancelled documents of a selection in one currency."""

    currency: Currency
    count: int
    total: Money
    open: Money


@dataclass(frozen=True, slots=True)
class DocumentFacets:
    """What a list shows around its rows: totals, counts per status and the years."""

    totals: list[CurrencyTotals]
    """Of the whole selection (all pages), including the status filter."""
    status_counts: dict[DisplayStatus, int]
    """Of the selection without the status filter, for the view buttons.

    Cancellation invoices are not counted: the views per status show invoices only.
    """
    years: list[int]
    """Years with documents of the selected types, newest first."""


@dataclass(frozen=True, slots=True)
class CurrencyFigures:
    currency: Currency
    open: Money
    overdue: Money
    paid: Money
    open_count: int
    overdue_count: int


@dataclass(frozen=True, slots=True)
class MonthlyRevenue:
    month: date
    """First day of the month."""
    currency: Currency
    net: Money


@dataclass(frozen=True, slots=True)
class CustomerRevenue:
    customer_id: UUID
    customer_name: str
    """As on the latest document."""
    currency: Currency
    net: Money


class DocumentRepository(Protocol):
    def get(self, document_id: UUID, *, for_update: bool = False) -> Document | None: ...
    def add(self, document: Document, index: DocumentIndex) -> None: ...
    def update(self, document: Document, index: DocumentIndex) -> None: ...
    def delete(self, document_id: UUID) -> None: ...
    def number_exists(self, document_type: DocumentType, number: str) -> bool: ...
    def latest_issue_date(self, document_type: DocumentType) -> date | None:
        """Issue date of the most recently dated issued document of the type."""
        ...

    def search(self, query: DocumentQuery) -> Page[DocumentSummary]: ...
    def facets(self, query: DocumentQuery) -> DocumentFacets: ...
    def get_pdf(self, document_id: UUID) -> bytes | None:
        """Return the archived PDF of an issued document, if there is one."""
        ...

    def archive_pdf(
        self, document: Document, content: bytes, e_invoice: bytes | None = None
    ) -> None:
        """Store the PDF, its embedded e-invoice and the hash; none can be replaced."""
        ...

    def get_e_invoice(self, document_id: UUID) -> bytes | None:
        """Return the e-invoice embedded in the archived PDF, if there is one."""
        ...

    def figures(self, today: date) -> list[CurrencyFigures]: ...
    def revenue_by_month(self, since: date) -> list[MonthlyRevenue]: ...
    def revenue_by_customer(self, since: date) -> list[CustomerRevenue]:
        """Net revenue per customer and currency of the invoices and cancellations since."""
        ...

    def revenue_between(self, start: date, end: date) -> dict[Currency, Money]:
        """Net revenue per currency of the invoices and cancellations issued in the days."""
        ...

    def days_to_pay(self, since: date) -> list[tuple[Currency, int]]:
        """Days from issuing to the last payment of the invoices fully paid since."""
        ...

    def recent_events(self, limit: int, today: date) -> list[tuple[DocumentSummary, str, datetime]]:
        """Latest events across all documents: (document, event kind, time)."""
        ...
