"""Invented invoices of a program used before, for the demo of taking them over (ADR 0019).

The demo company "used" another program until three years ago: a few of its invoices come
over through the regular invoice import, with a PDF each that looks like such a program's
output and a payment reminder as attachment. Names, numbers and amounts are made up.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from rhinvoice.application.importing.files import ImportFile
from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import round_half_up
from rhinvoice.domain.tax.category import TaxCategory

if TYPE_CHECKING:
    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.customer.customer import Customer

YEARS_BACK = 3
PAYMENT_TERMS = timedelta(days=14)
CENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class OldInvoice:
    counter: int
    month: int
    day: int
    customer: int | None
    """Index of a demo customer; None: a former customer the demo does not know."""
    net: Decimal
    text: str
    reminder: bool = False


OLD_INVOICES = (
    OldInvoice(
        117, 3, 14, 0, Decimal("2400.00"), "Neue Website, Gestaltung und Umsetzung", reminder=True
    ),
    OldInvoice(142, 6, 2, None, Decimal("680.00"), "Speisekarte und Flyer, Gestaltung"),
    OldInvoice(163, 9, 21, 2, Decimal("360.00"), "Hosting und Wartung, Juli bis September"),
)
FORMER_CUSTOMER = "Pension Bergruh (geschlossen)"


def _pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def old_pdf(lines: list[str]) -> bytes:
    """Write a one-page PDF with lines of text, like a plain invoice of an older program."""
    commands = [
        "BT",
        "/F1 11 Tf",
        "14 TL",
        "60 780 Td",
        *(f"({_pdf_text(line)}) Tj T*" for line in lines),
        "ET",
    ]
    stream = "\n".join(commands)
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R"
            " /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    body = b"%PDF-1.4\n"
    offsets: list[int] = []
    for number, content in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{number} 0 obj\n{content}\nendobj\n".encode("latin-1")
    xref = len(body)
    table = "".join(f"{offset:010d} 00000 n \n" for offset in offsets)
    body += (
        f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n{table}"
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode("latin-1")
    return body


def old_invoices(
    company: Company, customers: list[Customer], today: date
) -> tuple[bytes, tuple[ImportFile, ...]]:
    """Return the list (CSV) and the PDF files of the demo's old invoices."""
    year = today.year - YEARS_BACK
    currency = company.default_currency.value
    rows = ["Nummer;Datum;Fällig;Kunde;Strasse;PLZ;Ort;Netto;Betrag;Offen"]
    files: list[ImportFile] = []
    for old in OLD_INVOICES:
        number = f"RE-{year}-{old.counter}"
        issued = date(year, old.month, old.day)
        due = issued + PAYMENT_TERMS
        profile = profile_of(company.country)
        rate = profile.rates_on(issued).rate(TaxCategory.STANDARD)
        tax_name = profile.terms[Language.DE].tax_name
        total = old.net + round_half_up(old.net * rate / 100, CENT)
        if old.customer is None:
            name = FORMER_CUSTOMER
            street = "Bergweg 3"
            postal_code, city = company.address.postal_code, company.address.city
        else:
            customer = customers[old.customer]
            name = customer.display_name
            street = f"{customer.address.street} {customer.address.house_number}".strip()
            postal_code, city = customer.address.postal_code, customer.address.city
        rows.append(
            f"{number};{issued:%d.%m.%Y};{due:%d.%m.%Y};{name};{street};{postal_code};{city};"
            f"{old.net};{total};0"
        )
        text = [
            company.name,
            "",
            name,
            street,
            f"{postal_code} {city}",
            "",
            f"Rechnung {number}",
            f"Datum {issued:%d.%m.%Y}, zahlbar bis {due:%d.%m.%Y}",
            "",
            f"{old.text}: {currency} {old.net}",
            f"{tax_name} {rate} %: {currency} {total - old.net}",
            f"Total {currency} {total}",
        ]
        files.append(ImportFile(f"Rechnungen {year}/Rechnung {number}.pdf", old_pdf(text)))
        if old.reminder:
            reminder = [company.name, "", name, "", f"Zahlungserinnerung zu Rechnung {number}"]
            files.append(
                ImportFile(f"Rechnungen {year}/Zahlungserinnerung {number}.pdf", old_pdf(reminder))
            )
    return "\n".join(rows).encode(), tuple(files)
