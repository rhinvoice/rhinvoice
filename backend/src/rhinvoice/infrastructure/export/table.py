"""The export as a table of typed cells, shared by the Excel, CSV and PDF writers.

Amounts are Decimals with two places, dates are dates; each writer decides how to
write them. Text cells pass through ``neutralised`` where a spreadsheet could take
them for a formula (CSV).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from rhinvoice.domain.country.profile import NumberStyle
from rhinvoice.domain.country.registry import profile_of
from rhinvoice.infrastructure.export.labels import COLUMNS, KINDS, STATUSES, TREATMENTS

if TYPE_CHECKING:
    from datetime import date

    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.document.export import CurrencySum, ExportListing, ExportRow
    from rhinvoice.domain.shared.language import Language
    from rhinvoice.domain.shared.money import Money

type Cell = str | int | Decimal | date | None

CENT = Decimal("0.01")
FORMULA = re.compile(r"^[=+\-@\t\r]|[,;\t]\s*[=+\-@]")
"""What makes Excel or LibreOffice read a cell as a formula (OWASP: CSV injection): at the
start, or after a comma, semicolon or tab, where a spreadsheet with another separator
splits the value."""
TREATMENT_SEPARATOR = " / "


def neutralised(text: str) -> str:
    """Prefix text a spreadsheet would run as a formula with an apostrophe."""
    return f"'{text}" if FORMULA.search(text) else text


def decimal_separator(company: Company) -> str:
    """Return the company's: a point in CH and LI, a comma in DE and AT."""
    style = profile_of(company.country).number_style
    return "," if style is NumberStyle.DOT_COMMA else "."


def rate_text(rate: Decimal, separator: str) -> str:
    """E.g. "8.1 %" or "19 %"; trailing zeros dropped."""
    text = f"{rate.normalize():f}" if rate else "0"
    return text.replace(".", separator) + " %"


def _amount(value: Money | None) -> Decimal | None:
    return None if value is None else value.amount.quantize(CENT)


@dataclass(frozen=True, slots=True)
class Table:
    header: tuple[str, ...]
    rows: tuple[tuple[Cell, ...], ...]
    sum_rows: tuple[tuple[Cell, ...], ...]
    """One row per currency, in the columns of the list."""
    sums_header: tuple[str, ...]
    sums: tuple[tuple[Cell, ...], ...]
    """One row per currency, compact: currency, count and the amounts."""
    amount_columns: frozenset[int]
    """Indexes of the list's amount columns."""


@dataclass(frozen=True, slots=True)
class _Columns:
    labels: dict[str, str]
    rates: tuple[Decimal, ...]
    separator: str

    def rate_headers(self) -> list[str]:
        headers: list[str] = []
        for rate in self.rates:
            text = rate_text(rate, self.separator)
            headers += [
                self.labels["net_at"].format(rate=text),
                self.labels["tax_at"].format(rate=text),
            ]
        return headers


def table(listing: ExportListing, company: Company, language: Language) -> Table:
    labels = COLUMNS[language]
    columns = _Columns(labels, listing.rates, decimal_separator(company))
    lead = [
        labels[key]
        for key in (
            "number",
            "type",
            "date",
            "service_from",
            "service_to",
            "customer_number",
            "customer",
            "country",
            "vat_number",
            "currency",
            "treatment",
            "net",
        )
    ]
    # Pass-through items get a column only when the export holds some (ADR 0039).
    passed = [labels["pass_through"]] if listing.has_pass_through else []
    amounts = [*columns.rate_headers(), labels["tax"], *passed, labels["total"], labels["paid"]]
    tail = [labels["paid_on"], labels["open"], labels["written_off"], labels["status"]]
    header = [*lead, *amounts, *tail] + ([labels["file"]] if listing.with_files else [])
    first_amount = len(lead) - 1
    amount_columns = {
        *range(first_amount, first_amount + len(amounts) + 1),
        len(lead) + len(amounts) + 1,
        len(lead) + len(amounts) + 2,
    }
    return Table(
        header=tuple(header),
        rows=tuple(_row(row, listing, language) for row in listing.rows),
        sum_rows=tuple(_sum_row(found, listing, labels["sum"]) for found in listing.sums),
        sums_header=(
            labels["currency"],
            labels["count"],
            labels["net"],
            *columns.rate_headers(),
            labels["tax"],
            *passed,
            labels["total"],
            labels["paid"],
            labels["open"],
            labels["written_off"],
        ),
        sums=tuple(_sum(found, listing) for found in listing.sums),
        amount_columns=frozenset(amount_columns),
    )


def _rate_cells(row: ExportRow | CurrencySum, listing: ExportListing) -> list[Cell]:
    cells: list[Cell] = []
    for rate in listing.rates:
        found = row.at_rate(rate)
        cells += [None, None] if found is None else [_amount(found.net), _amount(found.tax)]
    return cells


def _pass_through(row: ExportRow | CurrencySum, listing: ExportListing) -> list[Cell]:
    return [_amount(row.pass_through)] if listing.has_pass_through else []


def _row(row: ExportRow, listing: ExportListing, language: Language) -> tuple[Cell, ...]:
    treatments = TREATMENT_SEPARATOR.join(
        TREATMENTS[language][treatment] for treatment in row.treatments
    )
    cells: list[Cell] = [
        row.number,
        KINDS[language][row.type],
        row.issue_date,
        row.service_from,
        row.service_to,
        row.customer_number,
        row.customer_name,
        row.country,
        row.customer_vat_number,
        row.currency.value,
        treatments,
        _amount(row.net),
        *_rate_cells(row, listing),
        _amount(row.tax),
        *_pass_through(row, listing),
        _amount(row.total),
        _amount(row.paid),
        row.paid_on,
        _amount(row.open),
        _amount(row.written_off),
        STATUSES[language][row.status],
    ]
    if listing.with_files:
        cells.append(row.file_name or "")
    return tuple(cells)


def _sum_row(found: CurrencySum, listing: ExportListing, label: str) -> tuple[Cell, ...]:
    cells: list[Cell] = [
        label,
        *([None] * 8),
        found.currency.value,
        None,
        _amount(found.net),
        *_rate_cells(found, listing),
        _amount(found.tax),
        *_pass_through(found, listing),
        _amount(found.total),
        _amount(found.paid),
        None,
        _amount(found.open),
        _amount(found.written_off),
        None,
    ]
    if listing.with_files:
        cells.append(None)
    return tuple(cells)


def _sum(found: CurrencySum, listing: ExportListing) -> tuple[Cell, ...]:
    return (
        found.currency.value,
        found.count,
        _amount(found.net),
        *_rate_cells(found, listing),
        _amount(found.tax),
        *_pass_through(found, listing),
        _amount(found.total),
        _amount(found.paid),
        _amount(found.open),
        _amount(found.written_off),
    )
