"""Persistence of documents with lines, payments and events."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    ColumnElement,
    Date,
    and_,
    case,
    cast,
    delete,
    func,
    insert,
    literal,
    or_,
    select,
    true,
    update,
)
from sqlalchemy.dialects.postgresql import aggregate_order_by

from rhinvoice.application.common import Page, SortDirection
from rhinvoice.application.document.ports import (
    BadDebt,
    CurrencyFigures,
    CurrencyTotals,
    CustomerRevenue,
    DocumentFacets,
    DocumentSort,
    DocumentSummary,
    MonthlyRevenue,
)
from rhinvoice.domain.catalog.unit import Unit
from rhinvoice.domain.document.attachment import Attachment
from rhinvoice.domain.document.document import (
    DisplayStatus,
    Document,
    DocumentEvent,
    DocumentOrigin,
    DocumentStatus,
    DocumentType,
    DraftContent,
    EventKind,
    Payment,
)
from rhinvoice.domain.document.lines import (
    Discount,
    DiscountKind,
    DocumentLine,
    LineKind,
    PriceMode,
)
from rhinvoice.domain.document.write_off import WriteOff, WriteOffReason
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency, Money
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply
from rhinvoice.domain.tax.treatment import TaxTreatment
from rhinvoice.infrastructure.db.search import NATURAL_COLLATION, prefix_query
from rhinvoice.infrastructure.db.serialization import (
    snapshot_from_json,
    snapshot_to_json,
    totals_from_json,
    totals_to_json,
)
from rhinvoice.infrastructure.db.tables import (
    document_attachments,
    document_events,
    document_lines,
    document_payments,
    document_pdfs,
    document_write_offs,
    documents,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime
    from uuid import UUID
    from zoneinfo import ZoneInfo

    from sqlalchemy import Connection, RowMapping

    from rhinvoice.application.document.ports import DocumentIndex, DocumentQuery

OPEN = (DocumentStatus.ISSUED.value, DocumentStatus.PARTIALLY_PAID.value)


def _search_vector(text: str) -> ColumnElement[Any]:
    """Both spellings are indexed: "Müller" is found by "muller" and "mueller"."""
    value = literal(text)
    return func.to_tsvector(
        "simple",
        func.rhinvoice_fold(value).op("||")(" ").op("||")(func.rhinvoice_fold_de(value)),
    )


FROZEN_COLUMNS = frozenset(
    {
        "id",
        "type",
        "number",
        "customer_id",
        "currency",
        "language",
        "price_mode",
        "treatment",
        "treatment_overridden",
        "goods_treatment",
        "discount_kind",
        "discount_value",
        "issue_date",
        "due_date",
        "service_from",
        "service_to",
        "subject",
        "reference",
        "intro_text",
        "payment_text",
        "closing_text",
        "created_at",
        "issued_at",
        "source_id",
        "snapshot",
        "issued_totals",
        "origin",
    }
)
"""Columns of issued documents that never change (see the trigger protect_document)."""


def _document_values(document: Document, index: DocumentIndex) -> dict[str, Any]:
    content = document.content
    return {
        "id": document.id,
        "type": document.type.value,
        "status": document.status.value,
        "number": document.number,
        "customer_id": content.customer_id,
        "currency": content.currency.value,
        "language": content.language.value,
        "price_mode": content.price_mode.value,
        "treatment": content.treatment.value,
        "treatment_overridden": content.treatment_overridden,
        "goods_treatment": (
            None if content.goods_treatment is None else content.goods_treatment.value
        ),
        "discount_kind": content.discount.kind.value,
        "discount_value": content.discount.value,
        "issue_date": content.issue_date,
        "due_date": content.due_date,
        "service_from": content.service_from,
        "service_to": content.service_to,
        "subject": content.subject,
        "reference": content.reference,
        "intro_text": content.intro_text,
        "payment_text": content.payment_text,
        "closing_text": content.closing_text,
        "created_at": document.created_at,
        "issued_at": document.issued_at,
        "source_id": document.source_id,
        "cancelled_by_id": document.cancelled_by_id,
        "converted_to_id": document.converted_to_id,
        "pdf_sha256": document.pdf_sha256,
        "origin": document.origin.value,
        "snapshot": None if document.snapshot is None else snapshot_to_json(document.snapshot),
        "issued_totals": (
            None if document.issued_totals is None else totals_to_json(document.issued_totals)
        ),
        "customer_name": index.customer_name[:200],
        "net_amount": index.net.amount,
        "total_amount": index.total.amount,
        "open_amount": index.open_amount.amount,
        "written_off_amount": index.written_off.amount,
        "search_vector": _search_vector(index.search_text),
    }


def _line_values(document_id: UUID, position: int, line: DocumentLine) -> dict[str, Any]:
    return {
        "id": line.id,
        "document_id": document_id,
        "position": position,
        "kind": line.kind.value,
        "description": line.description,
        "details": line.details,
        "quantity": line.quantity,
        "unit": None if line.unit is None else line.unit.code,
        "unit_price": line.unit_price,
        "discount_percent": line.discount_percent,
        "tax_category": line.tax_category.value,
        "supply": line.supply.value,
        "tax_rate": line.tax_rate,
        "article_id": line.article_id,
    }


def _line_from_row(row: RowMapping) -> DocumentLine:
    return DocumentLine(
        id=row["id"],
        kind=LineKind(row["kind"]),
        description=row["description"],
        details=row["details"],
        quantity=Decimal(row["quantity"]),
        unit=None if row["unit"] is None else Unit(row["unit"]),
        unit_price=Decimal(row["unit_price"]),
        discount_percent=Decimal(row["discount_percent"]),
        tax_category=TaxCategory(row["tax_category"]),
        supply=Supply(row["supply"]),
        article_id=row["article_id"],
        tax_rate=None if row["tax_rate"] is None else Decimal(row["tax_rate"]),
    )


def _write_off(row: RowMapping, currency: Currency) -> WriteOff:
    return WriteOff(
        id=row["id"],
        written_off_on=row["written_off_on"],
        amount=Money(Decimal(row["amount"]), currency),
        reason=WriteOffReason(row["reason"]),
        recorded_at=row["recorded_at"],
        note=row["note"],
    )


def _attachment(row: RowMapping) -> Attachment:
    return Attachment(
        id=row["id"],
        document_id=row["document_id"],
        file_name=row["file_name"],
        sha256=row["sha256"],
        size=row["size"],
        added_at=row["added_at"],
    )


def _display_status(
    document_type: str, status: str, due: date | None, today: date
) -> DisplayStatus:
    """Apply the rules of ``Document.display_status`` to a row."""
    late = due is not None and due < today and document_type != DocumentType.CANCELLATION.value
    if status in OPEN and late:
        return DisplayStatus.OVERDUE
    if status == DocumentStatus.SENT.value and late:
        return DisplayStatus.EXPIRED
    return DisplayStatus(status)


def _summary(row: RowMapping, today: date) -> DocumentSummary:
    currency = Currency(row["currency"])
    return DocumentSummary(
        id=row["id"],
        type=DocumentType(row["type"]),
        status=DocumentStatus(row["status"]),
        display_status=_display_status(row["type"], row["status"], row["due_date"], today),
        number=row["number"],
        customer_id=row["customer_id"],
        customer_name=row["customer_name"],
        subject=row["subject"],
        issue_date=row["issue_date"],
        due_date=row["due_date"],
        currency=currency,
        total=Money(Decimal(row["total_amount"]), currency),
        open_amount=Money(Decimal(row["open_amount"]), currency),
        created_at=row["created_at"],
        imported=row["origin"] == DocumentOrigin.IMPORTED.value,
    )


def _display_status_expression(today: date) -> ColumnElement[str]:
    """``_display_status`` as SQL, for counting per status."""
    late = and_(
        documents.c.due_date.is_not(None),
        documents.c.due_date < today,
        documents.c.type != DocumentType.CANCELLATION.value,
    )
    return case(
        (and_(documents.c.status.in_(OPEN), late), DisplayStatus.OVERDUE.value),
        (and_(documents.c.status == DocumentStatus.SENT.value, late), DisplayStatus.EXPIRED.value),
        else_=documents.c.status,
    )


def _document_date(zone: ZoneInfo) -> ColumnElement[date]:
    """Return the date a list groups by: the issue date, for drafts the creation date.

    The creation time is converted to the local date of the installation, so a
    draft created shortly after midnight on 1 January belongs to the new year.
    """
    created = func.timezone(zone.key, documents.c.created_at)
    return func.coalesce(documents.c.issue_date, cast(created, Date))


def _status_condition(status: DisplayStatus, today: date) -> ColumnElement[bool]:
    column = documents.c.status
    due = documents.c.due_date
    never_late = documents.c.type == DocumentType.CANCELLATION.value
    late = and_(due.is_not(None), due < today, ~never_late)
    not_late = or_(due.is_(None), due >= today, never_late)
    if status is DisplayStatus.OVERDUE:
        return and_(column.in_(OPEN), late)
    if status is DisplayStatus.EXPIRED:
        return and_(column == DocumentStatus.SENT.value, late)
    if status in {DisplayStatus.ISSUED, DisplayStatus.PARTIALLY_PAID, DisplayStatus.SENT}:
        return and_(column == status.value, not_late)
    return column == status.value


def _conditions(query: DocumentQuery, *, with_status: bool) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [
        documents.c.type.in_([document_type.value for document_type in query.types]),
    ]
    if with_status and query.statuses:
        conditions.append(or_(*(_status_condition(s, query.today) for s in query.statuses)))
    if query.customer_id is not None:
        conditions.append(documents.c.customer_id == query.customer_id)
    if query.origin is not None:
        conditions.append(documents.c.origin == query.origin.value)
    if query.year is not None:
        conditions.append(_document_date(query.zone) >= date(query.year, 1, 1))
        conditions.append(_document_date(query.zone) < date(query.year + 1, 1, 1))
    terms = prefix_query(query.search)
    if terms is not None:
        conditions.append(
            documents.c.search_vector.op("@@")(
                func.to_tsquery("simple", func.rhinvoice_fold(literal(terms))),
            ),
        )
    return conditions


_SORT: Mapping[DocumentSort, ColumnElement[Any]] = {
    DocumentSort.NUMBER: documents.c.number.collate(NATURAL_COLLATION),
    DocumentSort.ISSUE_DATE: documents.c.issue_date,
    DocumentSort.DUE_DATE: documents.c.due_date,
    DocumentSort.CUSTOMER: documents.c.customer_name.collate(NATURAL_COLLATION),
    DocumentSort.TOTAL: documents.c.total_amount,
    DocumentSort.CREATED_AT: documents.c.created_at,
}


class SqlDocumentRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    # --- Loading -----------------------------------------------------------------

    def get(self, document_id: UUID, *, for_update: bool = False) -> Document | None:
        statement = select(documents).where(documents.c.id == document_id)
        if for_update:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().first()
        if row is None:
            return None
        lines = self._connection.execute(
            select(document_lines)
            .where(document_lines.c.document_id == document_id)
            .order_by(document_lines.c.position),
        ).mappings()
        payments = self._connection.execute(
            select(document_payments)
            .where(document_payments.c.document_id == document_id)
            .order_by(document_payments.c.recorded_at, document_payments.c.id),
        ).mappings()
        events = self._connection.execute(
            select(document_events)
            .where(document_events.c.document_id == document_id)
            .order_by(document_events.c.id),
        ).mappings()
        write_off = (
            self._connection.execute(
                select(document_write_offs).where(document_write_offs.c.document_id == document_id),
            )
            .mappings()
            .first()
        )
        currency = Currency(row["currency"])
        content = DraftContent(
            customer_id=row["customer_id"],
            currency=currency,
            language=Language(row["language"]),
            price_mode=PriceMode(row["price_mode"]),
            lines=tuple(_line_from_row(line) for line in lines),
            treatment=TaxTreatment(row["treatment"]),
            treatment_overridden=row["treatment_overridden"],
            goods_treatment=(
                None if row["goods_treatment"] is None else TaxTreatment(row["goods_treatment"])
            ),
            discount=Discount(DiscountKind(row["discount_kind"]), Decimal(row["discount_value"])),
            issue_date=row["issue_date"],
            due_date=row["due_date"],
            service_from=row["service_from"],
            service_to=row["service_to"],
            subject=row["subject"],
            reference=row["reference"],
            intro_text=row["intro_text"],
            payment_text=row["payment_text"],
            closing_text=row["closing_text"],
        )
        return Document(
            id=row["id"],
            type=DocumentType(row["type"]),
            status=DocumentStatus(row["status"]),
            content=content,
            created_at=row["created_at"],
            number=row["number"],
            issued_at=row["issued_at"],
            snapshot=None if row["snapshot"] is None else snapshot_from_json(row["snapshot"]),
            issued_totals=(
                None if row["issued_totals"] is None else totals_from_json(row["issued_totals"])
            ),
            payments=tuple(
                Payment(
                    id=payment["id"],
                    paid_on=payment["paid_on"],
                    amount=Money(Decimal(payment["amount"]), currency),
                    recorded_at=payment["recorded_at"],
                    note=payment["note"],
                )
                for payment in payments
            ),
            events=tuple(
                DocumentEvent(at=event["at"], kind=EventKind(event["kind"]), detail=event["detail"])
                for event in events
            ),
            source_id=row["source_id"],
            cancelled_by_id=row["cancelled_by_id"],
            converted_to_id=row["converted_to_id"],
            pdf_sha256=row["pdf_sha256"],
            origin=DocumentOrigin(row["origin"]),
            write_off=None if write_off is None else _write_off(write_off, currency),
        )

    def number_exists(self, document_type: DocumentType, number: str) -> bool:
        condition = and_(documents.c.type == document_type.value, documents.c.number == number)
        return self._connection.execute(select(func.count()).where(condition)).scalar_one() > 0

    def latest_issue_date(self, document_type: DocumentType) -> date | None:
        statement = select(func.max(documents.c.issue_date)).where(
            documents.c.type == document_type.value,
            documents.c.status != DocumentStatus.DRAFT.value,
        )
        latest: date | None = self._connection.execute(statement).scalar_one()
        return latest

    # --- Saving ------------------------------------------------------------------

    def add(self, document: Document, index: DocumentIndex) -> None:
        self._connection.execute(insert(documents).values(_document_values(document, index)))
        self._insert_lines(document)
        self._sync_payments(document)
        self._sync_write_off(document)
        self._append_events(document, stored=0)

    def update(self, document: Document, index: DocumentIndex) -> None:
        stored_status = self._connection.execute(
            select(documents.c.status).where(documents.c.id == document.id),
        ).scalar_one()
        if stored_status == DocumentStatus.DRAFT.value:
            # Lines can only change while the stored document is a draft (also enforced
            # by a trigger); issuing freezes the tax rates in this last rewrite.
            self._connection.execute(
                delete(document_lines).where(document_lines.c.document_id == document.id),
            )
            self._insert_lines(document)
        stored_events = self._connection.execute(
            select(func.count()).where(document_events.c.document_id == document.id),
        ).scalar_one()
        values = _document_values(document, index)
        if stored_status != DocumentStatus.DRAFT.value:
            # Issued content is frozen (and guarded by a trigger): written once, never
            # again. Rewriting it would also change documents issued by an older version,
            # whose stored JSON lacks keys a newer version writes.
            values = {key: value for key, value in values.items() if key not in FROZEN_COLUMNS}
        self._connection.execute(
            update(documents).where(documents.c.id == document.id).values(values),
        )
        self._sync_payments(document)
        self._sync_write_off(document)
        self._append_events(document, stored=stored_events)

    def delete(self, document_id: UUID) -> None:
        self._connection.execute(delete(documents).where(documents.c.id == document_id))

    def _insert_lines(self, document: Document) -> None:
        if document.content.lines:
            self._connection.execute(
                insert(document_lines),
                [
                    _line_values(document.id, position, line)
                    for position, line in enumerate(document.content.lines)
                ],
            )

    def _sync_payments(self, document: Document) -> None:
        ids = [payment.id for payment in document.payments]
        self._connection.execute(
            delete(document_payments).where(
                document_payments.c.document_id == document.id,
                document_payments.c.id.not_in(ids) if ids else true(),
            ),
        )
        existing = set(
            self._connection.execute(
                select(document_payments.c.id).where(
                    document_payments.c.document_id == document.id
                ),
            ).scalars(),
        )
        new = [payment for payment in document.payments if payment.id not in existing]
        if new:
            self._connection.execute(
                insert(document_payments),
                [
                    {
                        "id": payment.id,
                        "document_id": document.id,
                        "paid_on": payment.paid_on,
                        "amount": payment.amount.amount,
                        "note": payment.note,
                        "recorded_at": payment.recorded_at,
                    }
                    for payment in new
                ],
            )

    def _sync_write_off(self, document: Document) -> None:
        """Store a new write-off, drop one that was taken back; a stored one never changes."""
        write_off = document.write_off
        self._connection.execute(
            delete(document_write_offs).where(
                document_write_offs.c.document_id == document.id,
                true() if write_off is None else document_write_offs.c.id != write_off.id,
            ),
        )
        if write_off is None:
            return
        stored = self._connection.execute(
            select(func.count()).where(document_write_offs.c.id == write_off.id),
        ).scalar_one()
        if not stored:
            self._connection.execute(
                insert(document_write_offs).values(
                    id=write_off.id,
                    document_id=document.id,
                    written_off_on=write_off.written_off_on,
                    amount=write_off.amount.amount,
                    reason=write_off.reason.value,
                    note=write_off.note,
                    recorded_at=write_off.recorded_at,
                ),
            )

    def _append_events(self, document: Document, *, stored: int) -> None:
        new = document.events[stored:]
        if new:
            self._connection.execute(
                insert(document_events),
                [
                    {
                        "document_id": document.id,
                        "at": event.at,
                        "kind": event.kind.value,
                        "detail": event.detail[:500],
                    }
                    for event in new
                ],
            )

    # --- Queries -----------------------------------------------------------------

    def search(self, query: DocumentQuery) -> Page[DocumentSummary]:
        statement = select(documents).where(and_(*_conditions(query, with_status=True)))
        total = self._connection.execute(
            select(func.count()).select_from(statement.subquery()),
        ).scalar_one()
        column = _SORT[query.sort]
        order = column.desc() if query.direction is SortDirection.DESC else column.asc()
        rows = self._connection.execute(
            statement.order_by(order.nulls_last(), documents.c.created_at.desc(), documents.c.id)
            .limit(query.page.limit)
            .offset(query.page.offset),
        ).mappings()
        return Page(items=[_summary(row, query.today) for row in rows], total=total)

    def get_pdf(self, document_id: UUID) -> bytes | None:
        statement = select(document_pdfs.c.content).where(
            document_pdfs.c.document_id == document_id
        )
        return self._connection.execute(statement).scalar_one_or_none()

    def get_e_invoice(self, document_id: UUID) -> bytes | None:
        statement = select(document_pdfs.c.e_invoice).where(
            document_pdfs.c.document_id == document_id
        )
        return self._connection.execute(statement).scalar_one_or_none()

    def archive_pdf(
        self, document: Document, content: bytes, e_invoice: bytes | None = None
    ) -> None:
        # The hash first: the trigger of document_pdfs checks the content against it.
        self._connection.execute(
            update(documents)
            .where(documents.c.id == document.id)
            .values(pdf_sha256=document.pdf_sha256),
        )
        self._connection.execute(
            insert(document_pdfs).values(
                document_id=document.id, content=content, e_invoice=e_invoice
            ),
        )

    def add_attachment(self, attachment: Attachment, content: bytes) -> None:
        # The trigger checks the content against the hash and refuses drafts.
        self._connection.execute(
            insert(document_attachments).values(
                id=attachment.id,
                document_id=attachment.document_id,
                file_name=attachment.file_name,
                sha256=attachment.sha256,
                content=content,
                added_at=attachment.added_at,
            ),
        )

    def attachments(self, document_id: UUID) -> list[Attachment]:
        statement = (
            select(
                document_attachments.c.id,
                document_attachments.c.document_id,
                document_attachments.c.file_name,
                document_attachments.c.sha256,
                func.length(document_attachments.c.content).label("size"),
                document_attachments.c.added_at,
            )
            .where(document_attachments.c.document_id == document_id)
            .order_by(document_attachments.c.file_name, document_attachments.c.id)
        )
        return [_attachment(row) for row in self._connection.execute(statement).mappings()]

    def get_attachment(
        self, document_id: UUID, attachment_id: UUID
    ) -> tuple[Attachment, bytes] | None:
        statement = select(
            document_attachments,
            func.length(document_attachments.c.content).label("size"),
        ).where(
            document_attachments.c.id == attachment_id,
            document_attachments.c.document_id == document_id,
        )
        row = self._connection.execute(statement).mappings().first()
        return None if row is None else (_attachment(row), bytes(row["content"]))

    def facets(self, query: DocumentQuery) -> DocumentFacets:
        return DocumentFacets(
            totals=self._totals(query),
            status_counts=self._status_counts(query),
            years=self._years(query),
        )

    def _totals(self, query: DocumentQuery) -> list[CurrencyTotals]:
        # Cancelled invoices and their cancellations net out; drafts are not issued yet.
        counted = and_(
            documents.c.status.not_in(
                [DocumentStatus.DRAFT.value, DocumentStatus.CANCELLED.value],
            ),
            documents.c.type != DocumentType.CANCELLATION.value,
        )
        statement = (
            select(
                documents.c.currency,
                func.count().label("count"),
                func.sum(documents.c.total_amount).label("total"),
                func.coalesce(
                    func.sum(case((documents.c.status.in_(OPEN), documents.c.open_amount))),
                    0,
                ).label("open"),
            )
            .where(and_(*_conditions(query, with_status=True)), counted)
            .group_by(documents.c.currency)
            .order_by(documents.c.currency)
        )
        result: list[CurrencyTotals] = []
        for row in self._connection.execute(statement).mappings():
            currency = Currency(row["currency"])
            result.append(
                CurrencyTotals(
                    currency=currency,
                    count=row["count"],
                    total=Money(Decimal(row["total"]), currency),
                    open=Money(Decimal(row["open"]), currency),
                ),
            )
        return result

    def _status_counts(self, query: DocumentQuery) -> dict[DisplayStatus, int]:
        status = _display_status_expression(query.today).label("display_status")
        statement = (
            select(status, func.count().label("count"))
            .where(
                and_(*_conditions(query, with_status=False)),
                documents.c.type != DocumentType.CANCELLATION.value,
            )
            .group_by(status)
        )
        return {
            DisplayStatus(row["display_status"]): row["count"]
            for row in self._connection.execute(statement).mappings()
        }

    def _years(self, query: DocumentQuery) -> list[int]:
        year = func.extract("year", _document_date(query.zone)).label("year")
        statement = (
            select(year)
            .distinct()
            .where(documents.c.type.in_([kind.value for kind in query.types]))
            .order_by(year.desc())
        )
        return [int(row) for row in self._connection.execute(statement).scalars()]

    def figures(self, today: date) -> list[CurrencyFigures]:
        invoices = documents.c.type == DocumentType.INVOICE.value
        is_open = documents.c.status.in_(OPEN)
        overdue = and_(is_open, documents.c.due_date < today)
        # What is written off was not paid: it is neither open nor received.
        paid = case(
            (
                documents.c.status.in_(
                    [*OPEN, DocumentStatus.PAID.value, DocumentStatus.WRITTEN_OFF.value]
                ),
                documents.c.total_amount - documents.c.open_amount - documents.c.written_off_amount,
            ),
            else_=0,
        )
        statement = (
            select(
                documents.c.currency,
                func.coalesce(func.sum(case((is_open, documents.c.open_amount), else_=0)), 0).label(
                    "open"
                ),
                func.coalesce(func.sum(case((overdue, documents.c.open_amount), else_=0)), 0).label(
                    "overdue"
                ),
                func.coalesce(func.sum(paid), 0).label("paid"),
                func.count().filter(is_open).label("open_count"),
                func.count().filter(overdue).label("overdue_count"),
            )
            .where(invoices, documents.c.status != DocumentStatus.DRAFT.value)
            .group_by(documents.c.currency)
            .order_by(documents.c.currency)
        )
        result: list[CurrencyFigures] = []
        for row in self._connection.execute(statement).mappings():
            currency = Currency(row["currency"])
            result.append(
                CurrencyFigures(
                    currency=currency,
                    open=Money(Decimal(row["open"]), currency),
                    overdue=Money(Decimal(row["overdue"]), currency),
                    paid=Money(Decimal(row["paid"]), currency),
                    open_count=row["open_count"],
                    overdue_count=row["overdue_count"],
                ),
            )
        return result

    def revenue_by_month(self, since: date) -> list[MonthlyRevenue]:
        month = func.date_trunc("month", documents.c.issue_date).label("month")
        statement = (
            select(month, documents.c.currency, func.sum(documents.c.net_amount).label("net"))
            .where(
                documents.c.type.in_([DocumentType.INVOICE.value, DocumentType.CANCELLATION.value]),
                documents.c.status != DocumentStatus.DRAFT.value,
                documents.c.issue_date >= since,
            )
            .group_by(month, documents.c.currency)
            .order_by(month, documents.c.currency)
        )
        return [
            MonthlyRevenue(
                month=row["month"].date(),
                currency=Currency(row["currency"]),
                net=Money(Decimal(row["net"]), Currency(row["currency"])),
            )
            for row in self._connection.execute(statement).mappings()
        ]

    def revenue_by_customer(self, since: date) -> list[CustomerRevenue]:
        statement = (
            select(
                documents.c.customer_id,
                documents.c.currency,
                func.sum(documents.c.net_amount).label("net"),
                # The name on the latest document (customers can be renamed).
                func.array_agg(
                    aggregate_order_by(
                        documents.c.customer_name,
                        documents.c.issue_date.desc(),
                        documents.c.created_at.desc(),
                    )
                )[1].label("latest_name"),
            )
            .where(
                documents.c.type.in_([DocumentType.INVOICE.value, DocumentType.CANCELLATION.value]),
                documents.c.status != DocumentStatus.DRAFT.value,
                documents.c.issue_date >= since,
            )
            .group_by(documents.c.customer_id, documents.c.currency)
            .order_by(func.sum(documents.c.net_amount).desc(), documents.c.customer_id)
        )
        return [
            CustomerRevenue(
                customer_id=row["customer_id"],
                customer_name=row["latest_name"],
                currency=Currency(row["currency"]),
                net=Money(Decimal(row["net"]), Currency(row["currency"])),
            )
            for row in self._connection.execute(statement).mappings()
        ]

    def revenue_between(self, start: date, end: date) -> dict[Currency, Money]:
        statement = (
            select(documents.c.currency, func.sum(documents.c.net_amount).label("net"))
            .where(
                documents.c.type.in_([DocumentType.INVOICE.value, DocumentType.CANCELLATION.value]),
                documents.c.status != DocumentStatus.DRAFT.value,
                documents.c.issue_date >= start,
                documents.c.issue_date <= end,
            )
            .group_by(documents.c.currency)
        )
        return {
            Currency(row["currency"]): Money(Decimal(row["net"]), Currency(row["currency"]))
            for row in self._connection.execute(statement).mappings()
        }

    def days_to_pay(self, since: date) -> list[tuple[Currency, int]]:
        last_payment = (
            select(
                document_payments.c.document_id,
                func.max(document_payments.c.paid_on).label("paid_on"),
            )
            .group_by(document_payments.c.document_id)
            .subquery()
        )
        statement = (
            select(
                documents.c.currency,
                (last_payment.c.paid_on - documents.c.issue_date).label("days"),
            )
            .join(last_payment, last_payment.c.document_id == documents.c.id)
            .where(
                documents.c.type == DocumentType.INVOICE.value,
                documents.c.status == DocumentStatus.PAID.value,
                # Imported invoices were paid on a day the program did not tell.
                documents.c.origin == DocumentOrigin.RHINVOICE.value,
                documents.c.id.not_in(select(document_write_offs.c.document_id)),
                last_payment.c.paid_on >= since,
            )
            .order_by(last_payment.c.paid_on, documents.c.id)
        )
        return [
            (Currency(row["currency"]), int(row["days"]))
            for row in self._connection.execute(statement).mappings()
        ]

    def bad_debts(self) -> list[BadDebt]:
        recovered: dict[UUID, list[tuple[date, Money]]] = {}
        payments = (
            select(
                document_payments.c.document_id,
                document_payments.c.paid_on,
                document_payments.c.amount,
                documents.c.currency,
            )
            .join(documents, documents.c.id == document_payments.c.document_id)
            .join(
                document_write_offs,
                document_write_offs.c.document_id == document_payments.c.document_id,
            )
            .where(document_payments.c.recorded_at > document_write_offs.c.recorded_at)
            .order_by(document_payments.c.recorded_at, document_payments.c.id)
        )
        for row in self._connection.execute(payments).mappings():
            recovered.setdefault(row["document_id"], []).append(
                (row["paid_on"], Money(Decimal(row["amount"]), Currency(row["currency"])))
            )
        statement = (
            select(document_write_offs, documents.c.currency, documents.c.issued_totals)
            .join(documents, documents.c.id == document_write_offs.c.document_id)
            .order_by(document_write_offs.c.written_off_on, document_write_offs.c.id)
        )
        return [
            BadDebt(
                write_off=_write_off(row, Currency(row["currency"])),
                totals=totals_from_json(row["issued_totals"]),
                recoveries=tuple(recovered.get(row["document_id"], ())),
            )
            for row in self._connection.execute(statement).mappings()
        ]

    def recent_events(self, limit: int, today: date) -> list[tuple[DocumentSummary, str, datetime]]:
        statement = (
            select(
                documents,
                document_events.c.kind.label("event_kind"),
                document_events.c.at.label("event_at"),
            )
            .join(document_events, document_events.c.document_id == documents.c.id)
            # An import of hundreds of old invoices is no news of the day.
            .where(document_events.c.kind != EventKind.IMPORTED.value)
            .order_by(document_events.c.at.desc(), document_events.c.id.desc())
            .limit(limit)
        )
        return [
            (_summary(row, today), row["event_kind"], row["event_at"])
            for row in self._connection.execute(statement).mappings()
        ]
