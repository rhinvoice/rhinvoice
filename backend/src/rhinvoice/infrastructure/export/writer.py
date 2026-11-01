"""The ``ExportWriter`` port: the list as Excel, CSV or PDF, and the ZIP with the PDFs.

- Excel: a sheet with the list (real numbers and dates, filter, frozen header) and a
  sheet with the sums per currency. Text is stored as text, never as a formula.
- CSV: UTF-8 with BOM (Excel recognises the encoding), semicolons, the company's
  decimal separator, ISO dates, no thousands separators; text a spreadsheet would run
  as a formula starts with an apostrophe. The sums per currency follow the list after
  an empty line.
- PDF: A4 landscape, printed by the Chromium of the documents (Gotenberg or a browser
  on this computer), with the company, the period, page numbers and the sums.
"""

from __future__ import annotations

import csv
import io
import tempfile
import zipfile
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, select_autoescape
from markupsafe import Markup
from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from rhinvoice.application.document.export import ExportFormat
from rhinvoice.application.errors import UnavailableError
from rhinvoice.infrastructure.export.labels import COLUMNS
from rhinvoice.infrastructure.export.printed import printed_list
from rhinvoice.infrastructure.export.table import (
    Cell,
    Table,
    decimal_separator,
    neutralised,
    table,
)
from rhinvoice.infrastructure.rendering.html import SANS_STACK, sans_fonts

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from typing import IO

    from openpyxl.worksheet.worksheet import Worksheet

    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.document.export import ExportListing
    from rhinvoice.domain.shared.language import Language
    from rhinvoice.infrastructure.rendering.pdf import PagePrinter

AMOUNT_FORMAT = "#,##0.00"
DATE_FORMAT = "yyyy-mm-dd"
SPOOL_BYTES = 16 * 1024 * 1024
"""ZIPs up to this size stay in memory, larger ones go to a temporary file."""
TEXT_WIDTH = 40
"""The widest an Excel column gets (characters)."""


class FileExportWriter:
    def __init__(self, printer: PagePrinter | None = None) -> None:
        """``printer``: None when no PDF service is configured (then no PDF lists)."""
        self._printer = printer
        self._environment = Environment(
            loader=PackageLoader("rhinvoice.infrastructure.export", "templates"),
            autoescape=select_autoescape(default=True, default_for_string=True),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def title(self, language: Language) -> str:
        return COLUMNS[language]["title"]

    def write(
        self,
        listing: ExportListing,
        company: Company,
        export_format: ExportFormat,
        language: Language,
    ) -> bytes:
        cells = table(listing, company, language)
        if export_format is ExportFormat.XLSX:
            return xlsx(cells, COLUMNS[language]["title"], COLUMNS[language]["sums_sheet"])
        if export_format is ExportFormat.CSV:
            return csv_file(cells, decimal_separator(company))
        if self._printer is None:
            raise UnavailableError("PDFs need the Gotenberg service (RHINVOICE_GOTENBERG_URL)")
        return self._printer.print_pdf(self.html(listing, company, language))

    def html(self, listing: ExportListing, company: Company, language: Language) -> str:
        """Render the list as an A4 landscape page for the PDF."""
        return self._environment.get_template("listing.html.j2").render(
            page=printed_list(listing, company, language),
            fonts=sans_fonts(),
            font_stack=Markup(SANS_STACK),  # noqa: S704 - a constant
        )

    def archive(self, files: Iterable[tuple[str, bytes]]) -> IO[bytes]:
        spooled = tempfile.SpooledTemporaryFile(max_size=SPOOL_BYTES)  # noqa: SIM115 - returned open
        try:
            with zipfile.ZipFile(spooled, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, content in files:
                    archive.writestr(name, content)
        except BaseException:
            # A PDF that cannot be had (no PDF service) ends the export: nothing is left open.
            spooled.close()
            raise
        spooled.seek(0)
        return spooled


# --- CSV ------------------------------------------------------------------------------------


def _csv_cell(cell: Cell, separator: str) -> str:
    if cell is None:
        return ""
    if isinstance(cell, Decimal):
        return f"{cell:f}".replace(".", separator)
    if isinstance(cell, date):
        return cell.isoformat()
    return neutralised(str(cell))


def csv_file(cells: Table, separator: str) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow([neutralised(name) for name in cells.header])
    for row in cells.rows:
        writer.writerow([_csv_cell(cell, separator) for cell in row])
    if cells.sum_rows:
        writer.writerow([])
        for row in cells.sum_rows:
            writer.writerow([_csv_cell(cell, separator) for cell in row])
    return output.getvalue().encode("utf-8-sig")


# --- Excel ----------------------------------------------------------------------------------


def _fill(sheet: Worksheet, header: Sequence[str], rows: Sequence[Sequence[Cell]]) -> None:
    sheet.append(list(header))
    widths = [len(name) for name in header]
    for values in rows:
        sheet.append(list(values))
        for index, (cell, value) in enumerate(zip(sheet[sheet.max_row], values, strict=True)):
            if isinstance(value, Decimal):
                cell.number_format = AMOUNT_FORMAT
            elif isinstance(value, date):
                cell.number_format = DATE_FORMAT
            elif isinstance(value, str):
                # A string from the data is text, also when it starts like a formula.
                cell.data_type = "s"
            widths[index] = max(widths[index], len("" if value is None else str(value)))
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = min(width + 2, TEXT_WIDTH)
    sheet.freeze_panes = "A2"
    if rows:
        sheet.auto_filter.ref = sheet.dimensions


def xlsx(cells: Table, title: str, sums_title: str) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.worksheets[0])
    _fill(workbook.create_sheet(title), cells.header, cells.rows)
    _fill(workbook.create_sheet(sums_title), cells.sums_header, cells.sums)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()
