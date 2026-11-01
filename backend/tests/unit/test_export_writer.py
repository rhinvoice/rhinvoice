"""The export files: Excel with real numbers, CSV for spreadsheets, the printed list, the ZIP."""

import csv
import io
import zipfile
from collections.abc import Iterator
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from rhinvoice.application.document.export import ExportFormat
from rhinvoice.application.errors import UnavailableError
from rhinvoice.domain.document.export import ExportListing, ExportPeriod, export_listing
from rhinvoice.domain.document.write_off import WriteOffReason
from rhinvoice.domain.shared.country import CountryCode
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from rhinvoice.infrastructure.export.table import neutralised, rate_text
from rhinvoice.infrastructure.export.writer import FileExportWriter
from tests.helpers import raises_exactly
from tests.unit.domain import factories
from tests.unit.domain.test_document import NOW, TODAY, issued, line, pay
from tests.unit.domain.test_export import cancelled
from tests.unit.domain.test_imported_document import imported

MARCH = ExportPeriod.month(2026, 3)
SWISS = factories.company()
GERMAN = factories.company(
    address=factories.address(country=CountryCode("DE"), postal_code="10115", city="Berlin")
)


class RecordingPrinter:
    def __init__(self) -> None:
        self.pages: list[str] = []

    def print_pdf(self, page: str) -> bytes:
        self.pages.append(page)
        return b"%PDF-1.7 list"


def listing(*, with_files: bool = False) -> ExportListing:
    """List a paid, a written-off and a cancelled invoice, its cancellation, euros, an import."""
    customer = factories.customer(company_name='=HYPERLINK("x")', number="-1")
    paid = pay(issued(service_from=date(2026, 2, 1), service_to=date(2026, 2, 28)), "1659.50")
    paid = replace(paid, snapshot=replace(paid.issued_snapshot, customer=customer))
    lost = pay(issued(), "659.50").record_write_off(new_id(), TODAY, WriteOffReason.GONE, NOW)
    invoice, cancellation = cancelled(issued(service_to=date(2026, 3, 1)))
    euro = issued(currency=Currency.EUR, lines=(line("2", "50"),))
    old = imported(issue_date=TODAY, due_date=TODAY)
    return export_listing(
        MARCH, [paid, lost, invoice, cancellation, euro, old], TODAY, with_files=with_files
    )


def rows(content: bytes) -> list[list[str]]:
    assert content.startswith(b"\xef\xbb\xbf")
    return list(csv.reader(io.StringIO(content.decode("utf-8-sig")), delimiter=";"))


# --- CSV ------------------------------------------------------------------------------------


def test_csv_for_a_swiss_company() -> None:
    content = FileExportWriter().write(listing(), SWISS, ExportFormat.CSV, Language.DE)
    assert b"\r\n" in content
    header, *lines = rows(content)
    assert header == [
        "Nummer",
        "Art",
        "Datum",
        "Leistung von",
        "Leistung bis",
        "Kundennummer",
        "Kunde",
        "Land",
        "UID/USt-IdNr.",
        "Währung",
        "Steuerfall",
        "Netto",
        "Netto 8.1 %",
        "Steuer 8.1 %",
        "Netto 2.6 %",
        "Steuer 2.6 %",
        "Steuer",
        "Brutto",
        "Bezahlt",
        "Bezahlt am",
        "Offen",
        "Abgeschrieben",
        "Status",
    ]
    by_number = {line[0]: line for line in lines if line}
    first = lines[0]
    # A text that starts like a formula is neutralised, amounts are plain numbers.
    assert first == [
        "R20150001",
        "Rechnung",
        "2026-03-09",
        "",
        "",
        "1001",
        "Beispiel AG",
        "CH",
        "",
        "CHF",
        "Inland",
        "1200.00",
        "",
        "",
        "",
        "",
        "96.00",
        "1296.00",
        "1296.00",
        "2026-03-09",
        "0.00",
        "",
        "Bezahlt",
    ]
    assert lines[1][5:7] == ["'-1", '\'=HYPERLINK("x")']
    assert lines[1][3:5] == ["2026-02-01", "2026-02-28"]
    assert lines[1][12:16] == ["1500.00", "121.50", "37.05", "0.96"]
    cancellation = by_number["S20260001"]
    assert cancellation[1] == "Storno"
    assert cancellation[11] == "-1537.05"
    assert cancellation[17] == "-1659.50"
    assert cancellation[22] == "Ausgestellt"
    written_off = [line for line in lines if line and line[22] == "Abgeschrieben"]
    assert written_off[0][21] == "1000.00"
    # The sums per currency follow after an empty line.
    blank = lines.index([])
    franc, euro = lines[blank + 1 :]
    assert franc[0] == "Summe"
    assert franc[9] == "CHF"
    assert franc[17] == "4615.00"
    assert franc[21] == "1000.00"
    assert euro[9] == "EUR"
    assert euro[12:14] == ["100.00", "8.10"]
    assert euro[14:16] == ["", ""]


def test_csv_for_a_german_company_writes_decimal_commas() -> None:
    content = FileExportWriter().write(listing(), GERMAN, ExportFormat.CSV, Language.EN)
    header, first, *_ = rows(content)
    assert header[11:16] == ["Net", "Net 8,1 %", "Tax 8,1 %", "Net 2,6 %", "Tax 2,6 %"]
    assert header[-3:] == ["Open", "Written off", "Status"]
    assert first[11] == "1200,00"
    assert first[1] == "Invoice"
    assert first[10] == "Domestic"


def test_csv_without_documents_has_only_the_header() -> None:
    empty = ExportListing(period=MARCH, rows=())
    content = FileExportWriter().write(empty, SWISS, ExportFormat.CSV, Language.FR)
    [header] = rows(content)
    assert header[0] == "Numéro"
    assert "Statut" in header


def test_with_files_the_list_names_each_file() -> None:
    content = FileExportWriter().write(
        listing(with_files=True), SWISS, ExportFormat.CSV, Language.IT
    )
    header, *lines = rows(content)
    assert header[-1] == "File"
    files = [line[-1] for line in lines if line]
    assert files[:6] == [
        "",
        "R20260001.pdf",
        "R20260001 (2).pdf",
        "R20260001 (3).pdf",
        "R20260001 (4).pdf",
        "S20260001.pdf",
    ]
    assert files[6:] == ["", ""]


@pytest.mark.parametrize("text", ["=1+1", "+41", "-5", "@SUM(A1)", "\tx", "\rx"])
def test_formulas_are_neutralised(text: str) -> None:
    assert neutralised(text) == f"'{text}"


@pytest.mark.parametrize("text", ["Muster,=HYPERLINK(1)", "a; +41", "x\t@SUM(A1)", "a, -5"])
def test_formulas_after_a_separator_are_neutralised(text: str) -> None:
    assert neutralised(text) == f"'{text}"


def test_plain_text_stays() -> None:
    assert neutralised("Müller, Meier & Co.") == "Müller, Meier & Co."
    assert neutralised("1-2") == "1-2"
    assert neutralised("Beispiel AG") == "Beispiel AG"
    assert neutralised("") == ""
    assert neutralised("a=b") == "a=b"


def test_rate_texts() -> None:
    assert rate_text(Decimal("8.10"), ".") == "8.1 %"
    assert rate_text(Decimal(20), ",") == "20 %"
    assert rate_text(Decimal("0.00"), ",") == "0 %"
    assert rate_text(Decimal("2.6"), ",") == "2,6 %"


# --- Excel ----------------------------------------------------------------------------------


def test_excel_holds_numbers_dates_and_text() -> None:
    content = FileExportWriter().write(listing(), SWISS, ExportFormat.XLSX, Language.DE)
    workbook = load_workbook(io.BytesIO(content))
    assert workbook.sheetnames == ["Rechnungen", "Summen"]
    sheet = workbook["Rechnungen"]
    assert sheet.freeze_panes == "A2"
    assert sheet.auto_filter.ref == sheet.dimensions
    assert sheet["A1"].value == "Nummer"
    assert sheet["C2"].value.date() == TODAY
    assert sheet["C2"].number_format == "yyyy-mm-dd"
    assert sheet["L2"].value == Decimal("1200.00") or sheet["L2"].value == 1200
    assert sheet["L2"].number_format == "#,##0.00"
    assert sheet["L2"].data_type == "n"
    # Text that looks like a formula stays text.
    assert sheet["G3"].value == '=HYPERLINK("x")'
    assert sheet["G3"].data_type == "s"
    assert sheet["F3"].value == "-1"
    assert sheet["D2"].value is None
    assert sheet.column_dimensions["A"].width == len("R20150001") + 2
    sums = workbook["Summen"]
    assert [cell.value for cell in sums[1]] == [
        "Währung",
        "Anzahl",
        "Netto",
        "Netto 8.1 %",
        "Steuer 8.1 %",
        "Netto 2.6 %",
        "Steuer 2.6 %",
        "Steuer",
        "Brutto",
        "Bezahlt",
        "Offen",
        "Abgeschrieben",
    ]
    assert [cell.value for cell in sums[2]][:3] == ["CHF", 5, 4274.1]
    assert sums["B2"].number_format == "General"
    assert sums["C2"].number_format == "#,##0.00"
    assert sums["A3"].value == "EUR"


def test_an_empty_excel_has_its_headers_without_filter() -> None:
    empty = ExportListing(period=MARCH, rows=())
    content = FileExportWriter().write(empty, SWISS, ExportFormat.XLSX, Language.EN)
    workbook = load_workbook(io.BytesIO(content))
    assert workbook.sheetnames == ["Invoices", "Totals"]
    assert workbook["Invoices"].max_row == 1
    assert workbook["Invoices"].auto_filter.ref is None


def test_long_texts_do_not_widen_a_column_without_end() -> None:
    customer = factories.customer(company_name="A" * 70)
    invoice = issued()
    invoice = replace(invoice, snapshot=replace(invoice.issued_snapshot, customer=customer))
    long = export_listing(MARCH, [invoice], TODAY, with_files=False)
    content = FileExportWriter().write(long, SWISS, ExportFormat.XLSX, Language.DE)
    assert load_workbook(io.BytesIO(content))["Rechnungen"].column_dimensions["G"].width == 40


# --- PDF ------------------------------------------------------------------------------------


def test_the_printed_list() -> None:
    printer = RecordingPrinter()
    writer = FileExportWriter(printer)
    company = replace(SWISS, name='Muster "&" <AG>')
    content = writer.write(listing(with_files=True), company, ExportFormat.PDF, Language.DE)
    assert content == b"%PDF-1.7 list"
    [page] = printer.pages
    assert "size: A4 landscape" in page
    assert '<html lang="de">' in page
    assert "Zeitraum: 01.03.2026 – 31.03.2026" in page  # noqa: RUF001 - the en dash
    # The company is escaped in the page and in the CSS string of the page margin.
    assert "Muster &#34;&amp;&#34; &lt;AG&gt; · Rechnungen" in page
    assert 'content: "Muster \\"\\26 \\" \\3C AG\\3E  · Rechnungen 01.03.2026' in page
    assert 'content: "Seite " counter(page) " / " counter(pages);' in page
    assert 'font-family: "Inter"' in page
    assert "1’537.05" in page  # noqa: RUF001 - the Swiss apostrophe
    assert "−1’659.50" in page  # noqa: RUF001 - minus and apostrophe
    assert '<span class="sub">Storno</span>' in page
    assert "01.02.2026 – 28.02.2026" in page  # noqa: RUF001
    assert '<span class="sub">– 01.03.2026</span>' not in page  # noqa: RUF001
    assert '<span class="sub">01.03.2026</span>' in page
    assert '<span class="sub">-1 · CH</span>' in page
    assert "R20260001 (2).pdf" in page
    assert "Summen pro Währung" in page
    assert '<th scope="col" class="amount">8.1 %<span class="sub">Netto / Steuer</span></th>' in (
        page
    )


def test_a_printed_list_in_german_style_and_without_documents() -> None:
    printer = RecordingPrinter()
    writer = FileExportWriter(printer)
    empty = ExportListing(period=MARCH, rows=())
    writer.write(empty, GERMAN, ExportFormat.PDF, Language.EN)
    writer.write(listing(), GERMAN, ExportFormat.PDF, Language.DE)
    empty_page, page = printer.pages
    assert "No invoices in this period." in empty_page
    assert "<table>" not in empty_page
    assert "1.537,05" in page
    assert "Datei" not in page


def test_without_a_pdf_service_there_is_no_printed_list() -> None:
    with raises_exactly(
        UnavailableError, "PDFs need the Gotenberg service (RHINVOICE_GOTENBERG_URL)"
    ):
        FileExportWriter().write(listing(), SWISS, ExportFormat.PDF, Language.DE)


# --- ZIP ------------------------------------------------------------------------------------


def test_the_zip_holds_the_files_in_order() -> None:
    archive = FileExportWriter().archive(
        iter([("Rechnungen 2026-03.csv", b"list"), ("R1.pdf", b"%PDF 1")])
    )
    with zipfile.ZipFile(archive) as opened:
        assert opened.namelist() == ["Rechnungen 2026-03.csv", "R1.pdf"]
        assert opened.read("R1.pdf") == b"%PDF 1"
    archive.close()


def test_titles() -> None:
    writer = FileExportWriter()
    assert [writer.title(language) for language in Language] == [
        "Rechnungen",
        "Invoices",
        "Factures",
        "Fatture",
    ]


def test_a_file_that_cannot_be_had_ends_the_zip() -> None:
    def files() -> Iterator[tuple[str, bytes]]:
        yield "list.csv", b"list"
        raise UnavailableError("the PDF service (Gotenberg) is not reachable")

    with raises_exactly(UnavailableError, "the PDF service (Gotenberg) is not reachable"):
        FileExportWriter().archive(files())
