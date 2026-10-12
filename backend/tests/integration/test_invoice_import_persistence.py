"""Imported invoices in PostgreSQL: origin, original PDF, attachments and their protection."""

import hashlib
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from rhinvoice.application.common import AddressInput
from rhinvoice.application.company.handlers import CompanyHandlers, SaveCompany
from rhinvoice.application.document.handlers import DocumentHandlers
from rhinvoice.application.document.ports import DocumentQuery
from rhinvoice.application.importing.fields import ImportTarget
from rhinvoice.application.importing.files import ImportFile
from rhinvoice.application.importing.handlers import ImportHandlers, ImportRequest
from rhinvoice.application.importing.results import RowStatus
from rhinvoice.domain.document.document import (
    DocumentOrigin,
    DocumentStatus,
    DocumentType,
    EventKind,
)
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from rhinvoice.infrastructure.db.uow import SqlUnitOfWork
from rhinvoice.infrastructure.importing.reader import SpreadsheetReader

CLOCK = FixedClock(datetime(2026, 3, 9, 9, 0, tzinfo=UTC))
BERN = AddressInput(postal_code="3011", city="Bern", country="CH")
PDF = b"%PDF-1.4 R20150001"
REMINDER = b"%PDF-1.4 reminder"
LIST = (
    b"Nummer;Datum;Kunde;PLZ;Ort;Netto;Betrag;Offen\n"
    b"R20150001;14.02.2015;Beispiel AG;3011;Bern;100;108;0\n"
    b"R20150002;20.02.2015;Beispiel AG;3011;Bern;50;54;54\n"
)
FILES = (
    ImportFile("2015/Rechnung R20150001.pdf", PDF),
    ImportFile("2015/Mahnung R20150001.pdf", REMINDER),
)


@pytest.fixture
def importer(engine: Engine) -> ImportHandlers:
    CompanyHandlers(uow=lambda: SqlUnitOfWork(engine)).save(
        SaveCompany(
            name="Muster GmbH",
            address=BERN,
            default_currency=Currency.CHF,
            default_language=Language.DE,
        )
    )
    return ImportHandlers(
        uow=lambda: SqlUnitOfWork(engine), clock=CLOCK, reader=SpreadsheetReader()
    )


def run(importer: ImportHandlers, *, commit: bool) -> list[RowStatus]:
    request = ImportRequest(ImportTarget.INVOICES, LIST, files=FILES, commit=commit)
    return [outcome.status for outcome in importer.run(request).outcomes]


def test_a_test_run_leaves_nothing_behind(engine: Engine, importer: ImportHandlers) -> None:
    assert run(importer, commit=False) == [RowStatus.NEW, RowStatus.NEW]
    with engine.connect() as connection:
        for table in ("documents", "document_pdfs", "document_attachments", "customers"):
            count = connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()  # noqa: S608 - fixed names
            assert count == 0, table


def test_imported_invoices_are_stored_with_their_files(
    engine: Engine, importer: ImportHandlers
) -> None:
    assert run(importer, commit=True) == [RowStatus.NEW, RowStatus.NEW]
    # Imported again, nothing changes.
    assert run(importer, commit=True) == [RowStatus.SKIPPED, RowStatus.SKIPPED]
    documents = DocumentHandlers(uow=lambda: SqlUnitOfWork(engine), clock=CLOCK)
    with SqlUnitOfWork(engine) as uow:
        page = uow.documents.search(
            DocumentQuery(today=CLOCK.today(), types=frozenset({DocumentType.INVOICE}))
        )
        summaries = {summary.number: summary for summary in page.items}
        assert all(summary.imported for summary in summaries.values())
        assert (
            uow.documents.search(
                DocumentQuery(
                    today=CLOCK.today(),
                    types=frozenset({DocumentType.INVOICE}),
                    origin=DocumentOrigin.RHINVOICE,
                )
            ).total
            == 0
        )
        paid = uow.documents.get(summaries["R20150001"].id)
        assert paid is not None
        assert (paid.origin, paid.status) == (DocumentOrigin.IMPORTED, DocumentStatus.PAID)
        assert paid.pdf_sha256 == hashlib.sha256(PDF).hexdigest()
        assert uow.documents.get_pdf(paid.id) == PDF
        assert paid.content.lines == ()
        assert paid.issued_totals is not None
        assert str(paid.issued_totals.tax.amount) == "8.00"
        assert [event.kind for event in paid.events] == [EventKind.IMPORTED]
        [attachment] = uow.documents.attachments(paid.id)
        assert (attachment.file_name, attachment.size) == ("2015/Mahnung R20150001.pdf", 17)
        assert uow.documents.get_attachment(paid.id, attachment.id) == (attachment, REMINDER)
        assert uow.documents.get_attachment(summaries["R20150002"].id, attachment.id) is None
        # No news and no payment days: the old program did not tell them.
        assert uow.documents.recent_events(10, CLOCK.today()) == []
        assert uow.documents.days_to_pay(date(2000, 1, 1)) == []
        revenue = uow.documents.revenue_between(date(2015, 1, 1), date(2015, 12, 31))
        assert str(revenue[Currency.CHF].amount) == "150.00"

    # The open one is paid like any other, and takes a file afterwards.
    unpaid = summaries["R20150002"].id
    documents.mark_paid(unpaid, CLOCK.today())
    documents.add_file(unpaid, "Scan.pdf", b"%PDF-1.4 scan")
    documents.add_file(unpaid, "Mahnung.pdf", b"%PDF-1.4 mahnung")
    with SqlUnitOfWork(engine) as uow:
        assert uow.documents.get_pdf(unpaid) == b"%PDF-1.4 scan"
        assert [a.file_name for a in uow.documents.attachments(unpaid)] == ["Mahnung.pdf"]
        stored = uow.documents.get(unpaid)
        assert stored is not None
        assert stored.status is DocumentStatus.PAID
        assert [event.kind for event in stored.events][-2:] == [
            EventKind.FILE_ADDED,
            EventKind.FILE_ADDED,
        ]


def test_attachments_and_the_origin_are_protected(engine: Engine, importer: ImportHandlers) -> None:
    run(importer, commit=True)
    with engine.connect() as connection:
        document_id = connection.execute(
            text("SELECT id FROM documents WHERE number = 'R20150001'")
        ).scalar_one()

    def rejected(statement: str, message: str) -> None:
        with engine.begin() as connection, pytest.raises(IntegrityError, match=message):
            connection.execute(text(statement), {"id": document_id})

    rejected(
        "UPDATE document_attachments SET file_name = 'x' WHERE document_id = :id",
        "attachments cannot be changed or deleted",
    )
    rejected(
        "DELETE FROM document_attachments WHERE document_id = :id",
        "attachments cannot be changed or deleted",
    )
    rejected("TRUNCATE document_attachments", "attachments cannot be changed or deleted")
    rejected(
        "INSERT INTO document_attachments (id, document_id, file_name, sha256, content, added_at)"
        " VALUES (gen_random_uuid(), :id, 'x.pdf', repeat('a', 64), 'x', now())",
        "the attachment does not match its hash",
    )
    rejected(
        "UPDATE documents SET origin = 'rhinvoice' WHERE id = :id",
        "issued documents are immutable",
    )


def test_drafts_have_no_attachments(engine: Engine, importer: ImportHandlers) -> None:
    run(importer, commit=True)
    with engine.begin() as connection:
        customer_id = connection.execute(text("SELECT id FROM customers")).scalar_one()
        connection.execute(
            text(
                "INSERT INTO documents (id, type, status, customer_id, currency, language,"
                " price_mode, treatment, treatment_overridden, discount_kind, discount_value,"
                " created_at, net_amount, total_amount, open_amount, search_vector)"
                " VALUES ('00000000-0000-0000-0000-000000000001', 'invoice', 'draft', :customer,"
                " 'CHF', 'de', 'net', 'domestic', false, 'percent', 0, now(), 0, 0, 0, '')"
            ),
            {"customer": customer_id},
        )
    content = b"%PDF-1.4"
    with (
        engine.begin() as connection,
        pytest.raises(IntegrityError, match="drafts have no attachments"),
    ):
        connection.execute(
            text(
                "INSERT INTO document_attachments"
                " (id, document_id, file_name, sha256, content, added_at)"
                " VALUES (gen_random_uuid(), '00000000-0000-0000-0000-000000000001', 'x.pdf',"
                " :sha, :content, now())"
            ),
            {"sha": hashlib.sha256(content).hexdigest(), "content": content},
        )
