"""Importing the invoices of a program used before, with their PDF files."""

from datetime import date
from decimal import Decimal

import pytest

from rhinvoice.application.errors import ConflictError
from rhinvoice.application.importing import handlers as import_handlers
from rhinvoice.application.importing.fields import ImportTarget
from rhinvoice.application.importing.files import ImportFile
from rhinvoice.application.importing.handlers import (
    ImportHandlers,
    ImportRequest,
)
from rhinvoice.application.importing.invoices import name_key
from rhinvoice.application.importing.results import RowProblem, RowStatus
from rhinvoice.application.numbering import handlers as numbering
from rhinvoice.application.numbering.handlers import allocate_number
from rhinvoice.domain.customer.customer import CustomerKind
from rhinvoice.domain.document.document import DocumentStatus, DocumentType, EventKind
from rhinvoice.domain.numbering.sequence import NumberSequence, SequenceKind
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.country import CountryCode
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency, Money
from tests.helpers import raises_exactly
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.application.test_import_handlers import SemicolonReader, lines
from tests.unit.domain import factories

PDF = b"%PDF-1.4 "

# As older programs export them: a counter as "Rechnungsnummer", the number in the title.
INVOICES = lines(
    "Rechnungsnummer;Betreff;Rechnungsdatum;KndNr;KundeName;KundeAdresse;KndPlz;KndOrt;KndLand;"
    "Waehrung;GesSumNetto;TotMwst;GesamtBetrag;OffeneBetrag",
    "1;Rechnung R20150001;14.02.2015;0010;Bergbahnen Muster AG;;;;;CHF;1200.00;96.00;1296.00;0",
    "2;Rechnung R20150002;20.02.2015;;Holzbau Beispiel GmbH;;;;;EUR;60.00;0;60.00;60.00",
    "3;Rechnung R20150003;03.03.2015;0099;Neu Kunde AG;Dorfstrasse 1;9470;Buchs SG;Schweiz;"
    "CHF;100;8;108;8",
    "4;Rechnung R20150004;04.03.2015;;Neu Kunde AG;;;;;CHF;50;;50;",
    "5;Rechnung R20150005;05.03.2015;;;;;;;CHF;50;;50;",
    "6;Rechnung R20150006;06.03.2015;0010;Bergbahnen Muster AG;;;;;CHF;0;0;0;0",
    "7;Rechnung R20150001;14.02.2015;0010;Bergbahnen Muster AG;;;;;CHF;1;0;1;0",
)
FILES = (
    ImportFile("2015/Rechnung R20150001.pdf", PDF + b"1"),
    ImportFile("2015/Rechnung R20150001_mahnung.pdf", PDF + b"1m"),
    ImportFile("2015/Rechnung R20150003.pdf", PDF + b"3"),
    ImportFile("2015/Scan_0042.pdf", PDF + b"x"),
)


@pytest.fixture
def handlers(store: Store, clock: FixedClock) -> ImportHandlers:
    store.company = factories.company()
    known = factories.customer(number="0010", company_name="Bergbahnen Muster AG")
    archived = factories.customer(
        number="0020",
        company_name="Holzbau Beispiel GmbH",
        default_currency=Currency.EUR,
        default_language=Language.EN,
    ).archive()
    store.customers = {known.id: known, archived.id: archived}
    account = factories.bank_account(is_default=True)
    store.bank_accounts = {account.id: account}
    return ImportHandlers(
        uow=lambda: InMemoryUnitOfWork(store), clock=clock, reader=SemicolonReader()
    )


def invoices_request(**overrides: object) -> ImportRequest:
    values: dict[str, object] = {
        "target": ImportTarget.INVOICES,
        "content": INVOICES,
        "files": FILES,
        "commit": True,
    }
    values.update(overrides)
    return ImportRequest(**values)  # type: ignore[arg-type]  # test builder


def test_invoices_are_taken_over_with_their_pdf(handlers: ImportHandlers, store: Store) -> None:
    run = handlers.run(invoices_request())
    # The files tell the number column: the title, not the counter.
    assert run.mapping["number"] == 1
    assert "subject" not in run.mapping
    assert [(o.row, o.status, o.number, o.name) for o in run.outcomes] == [
        (2, RowStatus.NEW, "R20150001", "Bergbahnen Muster AG"),
        (3, RowStatus.NEW, "R20150002", "Holzbau Beispiel GmbH"),
        (4, RowStatus.NEW, "R20150003", "Neu Kunde AG"),
        (5, RowStatus.NEW, "R20150004", "Neu Kunde AG"),
        (6, RowStatus.ERROR, "R20150005", ""),
        (7, RowStatus.ERROR, "R20150006", "Bergbahnen Muster AG"),
        (8, RowStatus.SKIPPED, "R20150001", "Bergbahnen Muster AG"),
    ]
    first, second, third, fourth, no_customer, zero, _ = run.outcomes
    assert (first.detail, first.file, first.attachments, first.new_customer) == (
        "CHF 1296.00",
        "2015/Rechnung R20150001.pdf",
        1,
        False,
    )
    assert (second.file, second.attachments, second.new_customer) == (None, 0, False)
    assert (third.file, third.new_customer, fourth.new_customer) == (
        "2015/Rechnung R20150003.pdf",
        True,
        False,
    )
    assert no_customer.problem == RowProblem(
        "customer_name", "required", "customer_name is required", ""
    )
    assert zero.problem == RowProblem(
        "total_amount", "non_positive_total", "the total of an invoice must be positive", "0"
    )
    assert run.unused_files == ("2015/Scan_0042.pdf",)
    assert run.next_number == "R20260001"
    assert run.committed

    documents = {stored.document.number or "": stored for stored in store.documents.values()}
    assert sorted(documents) == ["R20150001", "R20150002", "R20150003", "R20150004"]
    paid = documents["R20150001"].document
    assert paid.is_imported
    assert paid.status is DocumentStatus.PAID
    assert paid.content.issue_date == date(2015, 2, 14)
    assert paid.content.due_date == date(2015, 2, 14)
    assert paid.content.subject == ""
    assert paid.issued_snapshot.bank_account is not None
    assert store.pdfs[paid.id] == PDF + b"1"
    [(attachment, content)] = store.attachments.values()
    assert (attachment.document_id, attachment.file_name, content) == (
        paid.id,
        "2015/Rechnung R20150001_mahnung.pdf",
        PDF + b"1m",
    )
    assert documents["R20150001"].index.net == Money(Decimal("1200.00"), Currency.CHF)

    # The currency and language of the customer when the file has none.
    open_eur = documents["R20150002"].document
    assert (open_eur.status, open_eur.content.currency, open_eur.content.language) == (
        DocumentStatus.ISSUED,
        Currency.EUR,
        Language.EN,
    )
    assert open_eur.issued_snapshot.bank_account is None
    assert open_eur.id not in store.pdfs

    partly = documents["R20150003"].document
    assert partly.status is DocumentStatus.PARTIALLY_PAID
    assert partly.events[0].detail == "2015/Rechnung R20150003.pdf"
    # Without a net amount nor tax the total counts as net; without an open amount it is paid.
    later = documents["R20150004"]
    assert later.index.net == Money(Decimal(50), Currency.CHF)
    assert later.document.status is DocumentStatus.PAID
    assert later.document.events[0].detail == ""


def test_unknown_customers_are_created_and_archived(handlers: ImportHandlers, store: Store) -> None:
    handlers.run(invoices_request())
    created = [c for c in store.customers.values() if c.company_name == "Neu Kunde AG"]
    [customer] = created
    assert customer.archived
    assert customer.number == "0099"
    assert customer.kind is CustomerKind.COMPANY
    address = customer.address
    assert (address.street, address.house_number, address.postal_code, address.city) == (
        "Dorfstrasse",
        "1",
        "9470",
        "Buchs SG",
    )
    assert address.country == CountryCode("CH")
    # Customer since the first invoice.
    assert customer.created_at.date() == date(2015, 3, 3)
    snapshot = next(
        s.document.issued_snapshot.customer
        for s in store.documents.values()
        if s.document.number == "R20150003"
    )
    assert snapshot.number == "0099"


def test_a_taken_customer_number_gives_the_next_free_one(
    handlers: ImportHandlers, store: Store
) -> None:
    content = lines(
        "Nummer;Datum;Kundennummer;Kunde;PLZ Ort;Betrag",
        "R1001;01.01.2020;0010;Bergbahnen Muster;8000 Zürich;10",
        "R1002;01.01.2020;0020;;;10",
        "R1003;01.01.2020;0777;Ganz Neu AG;CH-8000 Zürich;10",
        "R1004;01.01.2020;;Bergbahnen  muster ag.;;10",
    )
    run = handlers.run(invoices_request(content=content, files=()))
    assert [o.status for o in run.outcomes] == [RowStatus.NEW] * 4
    # Found by number, however the file names it.
    assert [o.name for o in run.outcomes] == [
        "Bergbahnen Muster AG",
        "Holzbau Beispiel GmbH",
        "Ganz Neu AG",
        "Bergbahnen Muster AG",
    ]
    assert run.outcomes[2].new_customer
    created = next(c for c in store.customers.values() if c.company_name == "Ganz Neu AG")
    assert created.number == "0777"
    assert (created.address.postal_code, created.address.city) == ("8000", "Zürich")


def test_a_number_of_another_customer_is_not_taken_for_a_new_one(
    handlers: ImportHandlers, store: Store
) -> None:
    content = lines(
        "Nummer;Datum;Kunde;PLZ;Ort;Betrag",
        "R1001;01.01.2020;Ganz Neu AG;8000;Zürich;10",
        "R1002;01.01.2020;Noch Neuer AG;8000;Zürich;10",
    )
    run = handlers.run(invoices_request(content=content, files=()))
    assert [o.status for o in run.outcomes] == [RowStatus.NEW, RowStatus.NEW]
    numbers = sorted(c.number for c in store.customers.values())
    assert numbers == ["0010", "0020", "1001", "1002"]


def test_errors_name_the_column(handlers: ImportHandlers) -> None:
    content = lines(
        "Nummer;Datum;Fällig;Kunde;Netto;Betrag;Offen;Währung",
        ";01.01.2020;;Bergbahnen Muster AG;;10;;",
        "R1;morgen;;Bergbahnen Muster AG;;10;;",
        "R2;01.01.2020;1.1.2019;Bergbahnen Muster AG;;10;;",
        "R3;01.01.2020;;Bergbahnen Muster AG;20;10;;",
        "R4;01.01.2020;;Bergbahnen Muster AG;;10;11;",
        "R5;01.01.2020;;Bergbahnen Muster AG;;zehn;;",
        "R6;01.01.2020;;Unbekannt AG;;10;;",
        "R7;01.01.2020;;Bergbahnen Muster AG;;10.001;;",
        "R8;01.01.2020;;Bergbahnen Muster AG;;;;",
    )
    run = handlers.run(invoices_request(content=content, files=()))
    assert [(o.number, o.problem.field, o.problem.code) for o in run.outcomes if o.problem] == [
        ("", "number", "required"),
        ("R1", "issue_date", "invalid_date"),
        ("R2", "due_date", "invalid"),
        ("R3", "net_amount", "net_above_total"),
        ("R4", "open_amount", "open_above_total"),
        ("R5", "total_amount", "invalid_amount"),
        ("R6", "postal_code", "required"),
        ("R7", "total_amount", "invalid"),
        ("R8", "total_amount", "required"),
    ]


def test_a_test_run_changes_nothing(handlers: ImportHandlers, store: Store) -> None:
    run = handlers.run(invoices_request(commit=False))
    assert not run.committed
    assert run.count(RowStatus.NEW) == 4
    assert store.documents == {}
    assert store.pdfs == {}
    assert len(store.customers) == 2


def test_the_invoice_sequence_continues_behind_the_imported_numbers(
    handlers: ImportHandlers, store: Store
) -> None:
    content = lines(
        "Nummer;Datum;Kunde;Betrag",
        "R20260001;01.01.2026;Bergbahnen Muster AG;10",
        "R20260002;02.01.2026;Bergbahnen Muster AG;10",
        "R20250009;02.01.2025;Bergbahnen Muster AG;10",
    )
    run = handlers.run(invoices_request(content=content, files=()))
    assert run.next_number == "R20260003"
    sequence = store.sequences[SequenceKind.INVOICE]
    assert sequence.preview(date(2026, 3, 9)) == "R20260003"
    # The next invoice written here gets it.
    assert (
        sequence
        == NumberSequence.default(SequenceKind.INVOICE)
        .allocate(date(2026, 3, 9))[1]
        .allocate(date(2026, 3, 9))[1]
    )


def test_without_files_the_number_column_is_the_named_one(handlers: ImportHandlers) -> None:
    run = handlers.run(invoices_request(files=(), commit=False))
    assert run.mapping["number"] == 0
    assert run.mapping["subject"] == 1


def test_a_better_named_column_keeps_the_numbers(handlers: ImportHandlers) -> None:
    content = lines(
        "Rechnungsnummer;Betreff;Datum;Kunde;Betrag",
        "R20150001;Rechnung R20150001;14.02.2015;Bergbahnen Muster AG;10",
    )
    run = handlers.run(invoices_request(content=content, commit=False))
    assert (run.mapping["number"], run.mapping["subject"]) == (0, 1)


def test_needed_columns_are_reported(handlers: ImportHandlers) -> None:
    run = handlers.run(invoices_request(content=lines("Nummer;Kunde", "R1;Muster"), commit=False))
    assert run.missing == (("issue_date",), ("total_amount",))
    run = handlers.run(
        invoices_request(content=lines("Nummer;Datum;Betrag", "R1;1.1.2020;1"), commit=False)
    )
    assert run.missing == (("customer_number", "customer_name"),)


def test_files_are_checked(handlers: ImportHandlers, monkeypatch: pytest.MonkeyPatch) -> None:
    with raises_exactly(ValidationError, "Scan.pdf is no PDF file") as caught:
        handlers.run(invoices_request(files=(ImportFile("a/Scan.pdf", b"PNG"),)))
    assert (caught.value.field, caught.value.code) == ("files", "not_a_pdf")
    # Exactly at the limits is fine.
    monkeypatch.setattr(import_handlers, "MAX_FILES", 1)
    monkeypatch.setattr(import_handlers, "MAX_FILE_BYTES", len(PDF))
    handlers.run(invoices_request(files=(ImportFile("a.pdf", PDF),), commit=False))
    monkeypatch.setattr(import_handlers, "MAX_FILES", 5000)
    monkeypatch.setattr(import_handlers, "MAX_FILE_BYTES", len(PDF))
    with raises_exactly(ValidationError, "big.pdf is larger than 20 MB") as caught:
        handlers.run(invoices_request(files=(ImportFile("big.pdf", PDF + b"x"),)))
    assert (caught.value.field, caught.value.code) == ("files", "file_too_large")
    monkeypatch.setattr(import_handlers, "MAX_FILES", 1)
    with raises_exactly(ValidationError, "at most 1 files per import") as caught:
        handlers.run(invoices_request(files=(ImportFile("a.pdf", PDF), ImportFile("b.pdf", PDF))))
    assert (caught.value.field, caught.value.code) == ("files", "too_many_files")


def test_the_company_must_be_set_up(store: Store, clock: FixedClock) -> None:
    handlers = ImportHandlers(
        uow=lambda: InMemoryUnitOfWork(store), clock=clock, reader=SemicolonReader()
    )
    with pytest.raises(ConflictError):
        handlers.run(invoices_request())


def test_files_are_left_out_of_other_imports(handlers: ImportHandlers) -> None:
    content = lines("Firma;PLZ;Ort", "Muster AG;8000;Zürich")
    run = handlers.run(
        ImportRequest(target=ImportTarget.CUSTOMERS, content=content, files=FILES, commit=True)
    )
    assert (run.unused_files, run.next_number) == ((), None)
    assert run.mapping == {"company_name": 0, "postal_code": 1, "city": 2}


def test_imported_invoices_are_no_news(handlers: ImportHandlers, store: Store) -> None:
    handlers.run(invoices_request())
    with InMemoryUnitOfWork(store) as uow:
        assert uow.documents.recent_events(10, date(2026, 3, 9)) == []
        assert uow.documents.days_to_pay(date(2000, 1, 1)) == []
        document = next(iter(store.documents.values())).document
        assert document.type is DocumentType.INVOICE
        assert document.events[0].kind is EventKind.IMPORTED


def test_names_are_compared_without_case_and_punctuation() -> None:
    assert name_key("Bergbahnen  Muster AG.") == name_key("bergbahnen muster ag")
    assert name_key("i-magazine AG") == name_key("[i]-magazine AG")
    assert name_key("Müller") != name_key("Muller")


def test_tax_currency_and_subject_come_from_their_columns(
    handlers: ImportHandlers, store: Store
) -> None:
    content = lines(
        "Nummer;Datum;Kunde;Währung;MwSt-Betrag;Betrag;Betreff",
        "R1001;01.02.2020;Bergbahnen Muster AG;EUR;19.00;119.00;Webseite",
    )
    run = handlers.run(invoices_request(content=content, files=()))
    assert run.outcomes[0].detail == "EUR 119.00"
    [stored] = store.documents.values()
    document = stored.document
    assert stored.index.net == Money(Decimal("100.00"), Currency.EUR)
    assert (document.content.currency, document.content.subject) == (Currency.EUR, "Webseite")
    known = next(c for c in store.customers.values() if c.number == "0010")
    assert document.content.customer_id == known.id
    assert document.issued_snapshot.company == store.company
    assert stored.index.customer_name == "Bergbahnen Muster AG"
    assert (document.created_at, document.events[0].at) == (NOW, NOW)
    assert document.payments[0].recorded_at == NOW


def test_numbers_taken_before_are_skipped(handlers: ImportHandlers) -> None:
    content = lines("Nummer;Datum;Kunde;Betrag", "R1001;01.02.2020;Bergbahnen Muster AG;10")
    handlers.run(invoices_request(content=content, files=()))
    again = handlers.run(invoices_request(content=content, files=()))
    [outcome] = again.outcomes
    assert (outcome.status, outcome.number, outcome.name, outcome.detail) == (
        RowStatus.SKIPPED,
        "R1001",
        "Bergbahnen Muster AG",
        "",
    )
    unnamed = handlers.run(
        invoices_request(
            content=lines("Nummer;Datum;Kundennummer;Betrag", "R1001;01.02.2020;0010;10"),
            files=(),
        )
    )
    assert unnamed.outcomes[0].name == ""


def test_attachments_are_kept_each_with_its_time(handlers: ImportHandlers, store: Store) -> None:
    files = (
        ImportFile("R20150001.pdf", PDF + b"1"),
        ImportFile("R20150001_mahnung.pdf", PDF + b"m"),
        ImportFile("R20150001_kopie.pdf", PDF + b"k"),
    )
    content = lines("Nummer;Datum;Kunde;Betrag", "R20150001;01.02.2015;Bergbahnen Muster AG;10")
    handlers.run(invoices_request(content=content, files=files))
    attachments = [attachment for attachment, _ in store.attachments.values()]
    assert len({attachment.id for attachment in attachments}) == 2
    assert {attachment.added_at for attachment in attachments} == {NOW}


def test_of_equal_columns_the_named_one_keeps_the_numbers(handlers: ImportHandlers) -> None:
    content = lines(
        "Betreff;Rechnungsnummer;Datum;Kunde;Betrag",
        "R20150001;R20150001;14.02.2015;Bergbahnen Muster AG;10",
    )
    run = handlers.run(invoices_request(content=content, commit=False))
    assert (run.mapping["number"], run.mapping["subject"]) == (1, 0)
    unnamed = lines(
        "Spalte;Ablage;Datum;Kunde;Betrag",
        "R20150001;R20150001;14.02.2015;Bergbahnen Muster AG;10",
    )
    # Without a named one, the first column that names the files.
    assert handlers.run(invoices_request(content=unnamed, commit=False)).mapping["number"] == 0


def test_a_new_customer_takes_the_country_and_city_of_the_file(
    handlers: ImportHandlers, store: Store
) -> None:
    content = lines(
        "Nummer;Datum;Kunde;Strasse;PLZ;Ort;Land;Betrag",
        "R1001;01.02.2020;Neu GmbH;Hafenstraße 3;88131;Lindau;Deutschland;10",
        "R1002;01.02.2020;Ohne Strasse AG;;9000;St. Gallen;;10",
    )
    handlers.run(invoices_request(content=content, files=()))
    by_name = {c.company_name: c for c in store.customers.values()}
    german = by_name["Neu GmbH"].address
    assert (german.country, german.city, german.street) == (
        CountryCode("DE"),
        "Lindau",
        "Hafenstraße",
    )
    swiss = by_name["Ohne Strasse AG"].address
    assert (swiss.country, swiss.street, swiss.house_number) == (CountryCode("CH"), "", "")


def test_a_customer_number_of_another_name_is_not_taken(
    handlers: ImportHandlers, store: Store
) -> None:
    content = lines(
        "Nummer;Datum;Kundennummer;Kunde;PLZ;Ort;Betrag",
        # The old program's 0010 is someone else than Rhinvoice's 0010.
        "R1001;01.01.2020;0010;Bäckerei Huber;8000;Zürich;10",
        # A renamed customer stays the same one.
        "R1002;01.01.2020;0020;Holzbau Beispiel AG;;;10",
        # The name finds the customer when the number belongs to another one.
        "R1003;01.01.2020;0020;Bergbahnen Muster AG;;;10",
    )
    run = handlers.run(invoices_request(content=content, files=()))
    assert [(o.name, o.new_customer) for o in run.outcomes] == [
        ("Bäckerei Huber", True),
        ("Holzbau Beispiel GmbH", False),
        ("Bergbahnen Muster AG", False),
    ]
    baker = next(c for c in store.customers.values() if c.company_name == "Bäckerei Huber")
    assert baker.number not in {"0010", "0020"}


def test_customer_errors_name_the_customer_columns(handlers: ImportHandlers) -> None:
    content = lines(
        "Nummer;Datum;Kundennummer;Kunde;PLZ;Ort;Betrag",
        f"R1001;01.01.2020;0099;{'x' * 300};8000;Zürich;10",
    )
    [outcome] = handlers.run(invoices_request(content=content, files=())).outcomes
    assert outcome.problem is not None
    assert outcome.problem.field == "customer_name"


def test_a_row_with_a_bad_file_name_writes_nothing(handlers: ImportHandlers, store: Store) -> None:
    files = (
        ImportFile("R20150001.pdf", PDF + b"1"),
        ImportFile(f"{'d' * 260}/R20150001_mahnung.pdf", PDF + b"m"),
    )
    content = lines("Nummer;Datum;Kunde;Betrag", "R20150001;01.02.2015;Bergbahnen Muster AG;10")
    [outcome] = handlers.run(invoices_request(content=content, files=files)).outcomes
    assert outcome.status is RowStatus.ERROR
    assert store.documents == {}
    assert store.pdfs == {}


def test_a_test_run_reports_the_files_without_storing_them(
    handlers: ImportHandlers, store: Store
) -> None:
    run = handlers.run(invoices_request(commit=False))
    assert run.outcomes[0].file == "2015/Rechnung R20150001.pdf"
    assert run.outcomes[0].attachments == 1
    assert (store.pdfs, store.attachments) == ({}, {})


def test_reminders_never_become_the_invoice(handlers: ImportHandlers, store: Store) -> None:
    files = (ImportFile("Mahnung R20150001.pdf", PDF + b"m"),)
    content = lines("Nummer;Datum;Kunde;Betrag", "R20150001;01.02.2015;Bergbahnen Muster AG;10")
    [outcome] = handlers.run(invoices_request(content=content, files=files)).outcomes
    assert (outcome.file, outcome.attachments) == (None, 1)
    [stored] = store.documents.values()
    assert stored.document.id not in store.pdfs
    assert stored.document.events[0].detail == ""


def test_imported_numbers_ahead_of_the_counter_are_passed_over(
    handlers: ImportHandlers, store: Store, clock: FixedClock
) -> None:
    content = lines(
        "Nummer;Datum;Kunde;Betrag",
        "R20260001;01.01.2026;Bergbahnen Muster AG;10",
        "R20260003;02.01.2026;Bergbahnen Muster AG;10",
    )
    run = handlers.run(invoices_request(content=content, files=()))
    assert run.next_number == "R20260002"
    with InMemoryUnitOfWork(store) as uow:
        assert allocate_number(uow, SequenceKind.INVOICE, clock.today()) == "R20260002"
        # The gap is filled, the imported number passed over.
        assert allocate_number(uow, SequenceKind.INVOICE, clock.today()) == "R20260004"


def test_the_counter_gives_up_after_a_long_run_of_used_numbers(
    handlers: ImportHandlers, store: Store, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = lines(
        "Nummer;Datum;Kunde;Betrag",
        "R20260001;01.01.2026;Bergbahnen Muster AG;10",
        "R20260002;01.01.2026;Bergbahnen Muster AG;10",
    )
    handlers.run(invoices_request(content=content, files=()))
    monkeypatch.setattr(numbering, "MAX_SKIPPED_NUMBERS", 1)
    store.sequences.pop(SequenceKind.INVOICE)
    with (
        InMemoryUnitOfWork(store) as uow,
        raises_exactly(ConflictError, "no free number found, please check the number sequence"),
    ):
        allocate_number(uow, SequenceKind.INVOICE, clock.today())


def test_without_a_matching_column_the_named_one_stays(handlers: ImportHandlers) -> None:
    content = lines("Datum;Kunde;Betrag", "01.01.2020;Bergbahnen Muster AG;10")
    run = handlers.run(invoices_request(content=content, commit=False))
    assert "number" not in run.mapping
    assert run.missing == (("number",),)
