"""The export as a printed list: the columns of the table, stacked to fit A4 landscape.

A cell holds a main line and a small second one: the kind under the number, the
customer's number, country and VAT ID under the name, the tax under the net amount of
each rate and the day of payment under what was paid. Nothing of the table is left out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from markupsafe import Markup

from rhinvoice.domain.country.registry import profile_of
from rhinvoice.infrastructure.export.labels import COLUMNS, KINDS, STATUSES, TREATMENTS
from rhinvoice.infrastructure.export.table import TREATMENT_SEPARATOR, decimal_separator, rate_text
from rhinvoice.infrastructure.rendering.formatting import PrintLocale, money
from rhinvoice.infrastructure.rendering.html import EN_DASH, SEPARATOR, css_string

if TYPE_CHECKING:
    from datetime import date

    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.document.export import CurrencySum, ExportListing, ExportRow
    from rhinvoice.domain.shared.language import Language
    from rhinvoice.domain.shared.money import Money


@dataclass(frozen=True, slots=True)
class PrintedCell:
    main: str
    sub: str = ""
    amount: bool = False


@dataclass(frozen=True, slots=True)
class PrintedList:
    language: str
    labels: dict[str, str]
    company: str
    period: str
    header: tuple[PrintedCell, ...]
    rows: tuple[tuple[PrintedCell, ...], ...]
    sums_header: tuple[PrintedCell, ...]
    sums: tuple[tuple[PrintedCell, ...], ...]
    footer: Markup
    """Company, title and period as the content of a CSS string (page margin)."""
    page_label: Markup


def day(value: date | None) -> str:
    return "" if value is None else f"{value.day:02d}.{value.month:02d}.{value.year}"


@dataclass(frozen=True, slots=True)
class _Printer:
    language: Language
    locale: PrintLocale
    listing: ExportListing

    def amount(self, value: Money | None, sub: Money | None = None) -> PrintedCell:
        return PrintedCell(
            main="" if value is None else money(value.amount, self.locale),
            sub="" if sub is None else money(sub.amount, self.locale),
            amount=True,
        )

    def rates(self, row: ExportRow | CurrencySum) -> list[PrintedCell]:
        cells: list[PrintedCell] = []
        for rate in self.listing.rates:
            found = row.at_rate(rate)
            cells.append(
                PrintedCell("", amount=True) if found is None else self.amount(found.net, found.tax)
            )
        return cells

    def row(self, row: ExportRow) -> tuple[PrintedCell, ...]:
        language = self.language
        customer = SEPARATOR.join(
            part for part in (row.customer_number, row.country, row.customer_vat_number) if part
        )
        service = (
            ""
            if row.service_from is None and row.service_to is None
            else f"{day(row.service_from)}{EN_DASH}{day(row.service_to)}".strip(EN_DASH)
        )
        cells = [
            PrintedCell(row.number, KINDS[language][row.type]),
            PrintedCell(day(row.issue_date), service),
            PrintedCell(row.customer_name, customer),
            PrintedCell(
                TREATMENT_SEPARATOR.join(TREATMENTS[language][found] for found in row.treatments)
            ),
            PrintedCell(row.currency.value),
            self.amount(row.net),
            *self.rates(row),
            self.amount(row.tax),
            self.amount(row.total),
            PrintedCell(money(row.paid.amount, self.locale), day(row.paid_on), amount=True),
            self.amount(row.open),
            self.amount(row.written_off),
            PrintedCell(STATUSES[language][row.status]),
        ]
        if self.listing.with_files:
            cells.append(PrintedCell(row.file_name or ""))
        return tuple(cells)

    def sum(self, found: CurrencySum) -> tuple[PrintedCell, ...]:
        return (
            PrintedCell(found.currency.value),
            PrintedCell(str(found.count), amount=True),
            self.amount(found.net),
            *self.rates(found),
            self.amount(found.tax),
            self.amount(found.total),
            self.amount(found.paid),
            self.amount(found.open),
            self.amount(found.written_off),
        )


def printed_list(listing: ExportListing, company: Company, language: Language) -> PrintedList:
    labels = COLUMNS[language]
    printer = _Printer(
        language, PrintLocale.of(language, profile_of(company.country).number_style), listing
    )
    separator = decimal_separator(company)
    net_tax = f"{labels['net']} / {labels['tax']}"
    rates = tuple(
        PrintedCell(rate_text(rate, separator), net_tax, amount=True) for rate in listing.rates
    )
    header = (
        PrintedCell(labels["number"], labels["type"]),
        PrintedCell(labels["date"], f"{labels['service_from']}{EN_DASH}{labels['service_to']}"),
        PrintedCell(
            labels["customer"],
            f"{labels['customer_number']}{SEPARATOR}{labels['country']}"
            f"{SEPARATOR}{labels['vat_number']}",
        ),
        PrintedCell(labels["treatment"]),
        PrintedCell(labels["currency"]),
        PrintedCell(labels["net"], amount=True),
        *rates,
        PrintedCell(labels["tax"], amount=True),
        PrintedCell(labels["total"], amount=True),
        PrintedCell(labels["paid"], labels["paid_on"], amount=True),
        PrintedCell(labels["open"], amount=True),
        PrintedCell(labels["written_off"], amount=True),
        PrintedCell(labels["status"]),
    ) + ((PrintedCell(labels["file"]),) if listing.with_files else ())
    sums_header = (
        PrintedCell(labels["currency"]),
        PrintedCell(labels["count"], amount=True),
        PrintedCell(labels["net"], amount=True),
        *rates,
        PrintedCell(labels["tax"], amount=True),
        PrintedCell(labels["total"], amount=True),
        PrintedCell(labels["paid"], amount=True),
        PrintedCell(labels["open"], amount=True),
        PrintedCell(labels["written_off"], amount=True),
    )
    period = f"{day(listing.period.start)}{EN_DASH}{day(listing.period.end)}"
    footer = f"{company.name}{SEPARATOR}{labels['title']} {period}"
    return PrintedList(
        language=language.value,
        labels=labels,
        company=company.name,
        period=period,
        footer=Markup(css_string(footer)),  # noqa: S704 - escaped for the CSS string
        page_label=Markup(css_string(labels["page"])),  # noqa: S704 - escaped likewise
        header=header,
        rows=tuple(printer.row(row) for row in listing.rows),
        sums_header=sums_header,
        sums=tuple(printer.sum(found) for found in listing.sums),
    )
