# 0038 – Export for bookkeeping

- Status: accepted
- Date: 2026-10-29

## Context
Users hand their invoices to a bookkeeper, a Swiss *Treuhand* or a tax adviser every month,
quarter or year (issue #47). Until now each invoice had to be downloaded on its own. The people
receiving the files work with Excel, with CSV imports into their accounting program, or simply
want a printable list and the PDFs.

## Decision
- **What is exported.** Issued invoices and cancellation invoices whose *issue date* lies in the
  period, also invoices taken over from a previous program (ADR 0019). Never drafts or quotes.
  The selection rule lives in the domain (`ExportPeriod.selects`); the repository mirrors it in SQL.
- **Period.** Month, quarter, year or free days; the dialog preselects the previous full month.
  The API takes only `start` and `end` (both included); the dialog turns its choice into them.
  At most ten years: from 29 February the limit is the 28th ten years later.
- **Formats.**
  - *Excel (.xlsx)* with openpyxl (already a dependency for the import): sheet 1 is the list
    (filter, frozen header), sheet 2 the sums per currency. Amounts are numbers with the format
    `#,##0.00`, dates are dates (`yyyy-mm-dd`). Text is stored as text (`data_type` "s"), so a
    value such as `=HYPERLINK(...)` is never a formula and keeps its content.
  - *CSV*: UTF-8 with BOM (Excel then reads umlauts right), `;` as separator, CRLF, dates
    `YYYY-MM-DD`, amounts without thousands separators with the decimal separator of the
    company's country (point in CH/LI, comma in DE/AT, from the country profile's number style).
    Text starting with `=`, `+`, `-`, `@`, tab or CR gets a leading apostrophe (OWASP CSV
    injection). Numbers are never prefixed, so negative amounts stay numbers.
  - *PDF*: A4 landscape, rendered by the same `PagePrinter` as the documents (Gotenberg or the
    local Chromium, ADR 0021), with the company, the period, page numbers in the page margin
    (`@page` margin boxes) and the sums per currency at the end. Cells are stacked (kind under
    the number, customer number, country and VAT ID under the name, tax under the net per rate,
    day of payment under what was paid) so that every column of the table fits.
  - *ZIP* (option "Rechnungs-PDFs als ZIP beilegen"): the list in the chosen format first, then
    the PDF of every document. Own documents add their archived PDF (archived now if it was not
    yet, as on a download); imported invoices their original. The files are named after the
    number with the characters `/\:*?"<>|` replaced; a name taken already (case-insensitive)
    gets " (2)", " (3)" … The column *Datei* exists only in ZIP exports, where it names
    something. An imported invoice without PDF leaves it empty. The ZIP is written into a
    spooled temporary file (in memory up to 16 MB), one PDF at a time, and streamed.
- **Sums per currency, never across currencies.** In Excel a separate sheet, so that the list
  stays one clean table for filters and pivot tables. CSV has no sheets: the sums follow the
  list after an empty line, one row per currency in the list's columns ("Summe" in *Nummer*).
- **Columns.** Nummer, Art, Datum, Leistung von, Leistung bis, Kundennummer, Kunde, Land,
  UID/USt-IdNr., Währung, Steuerfall, Netto, a pair *Netto x %* / *Steuer x %* per VAT rate that
  occurs in the export (0 % included: exempt revenue is what accountants ask for), Steuer,
  Brutto, Bezahlt, Bezahlt am, Offen, Abgeschrieben, Status, Datei. Headers follow the language of
  the program's interface (`language` parameter; the company's language by default).
  - Customer data are taken from the issue snapshot, as printed.
  - Amounts are as issued: cancellations are negative. *Brutto* is the payable total, Swiss
    cash rounding included, so *Netto* + *Steuer* may differ from it by up to 0.02.
  - *Bezahlt am* is the day of the last payment of a paid invoice, empty otherwise (also for
    written-off ones, which were not settled by a payment).
  - *Offen* of a cancellation is 0: it settles its invoice, nobody owes it.
  - *Abgeschrieben* is what is lost of a written-off invoice (write-off less later payments).
  - Imported invoices have no per-rate amounts: their lines were not taken over (ADR 0019).
- **API.** `GET /api/exports/invoices?start&end&format&pdfs&language`, authenticated, read-only
  (also in the demo), streamed with `Content-Disposition: attachment` built like the other
  downloads, `Cache-Control: no-store`. A reversed or too long period is a 422 with the codes
  `period_reversed` / `period_too_long`; a PDF list or a ZIP needing a PDF without a PDF service
  is a 503.
- **No DATEV or BMD export yet.** Their formats (DATEV-Format "Buchungsstapel", BMD import) need
  account numbers, tax keys and a chart of accounts that Rhinvoice does not know. They come only
  after asking tax advisers which fields they expect; until then Excel and CSV are the exchange.

## Consequences
- A month's invoices go to the bookkeeping in one download, with the PDFs if wanted.
- Taxes are reported as issued. Companies accounting by received payments read *Bezahlt* and
  *Bezahlt am*; payments on invoices of an earlier period appear in that period's export.
- A ZIP over many years may take a while when PDFs were never archived (no PDF service when
  issuing): each is rendered and archived once.
