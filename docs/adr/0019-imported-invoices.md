# 0019 – Invoices of a program used before

- Status: accepted
- Date: 2026-10-13

## Context
People who move to Rhinvoice bring years of invoices from another program and want to close that
program. The invoices have to stay readable for ten years (CH: OR 958f with the GeBüV, DE: § 147 AO,
AT: § 132 BAO), and they want to find them where their new ones are: in the invoice list, in the
customer's history, in the revenue of last year, and open ones must still be paid. Their content
exists twice: as the PDF the customer got and as a list (CSV or Excel) with number, date, customer
and amounts. Positions are rarely exported, and when they are, recalculating them with today's
templates and rounding would give a different invoice than the one that was sent.

## Decision
- **The original PDF is the invoice.** An imported invoice is an issued `Document` with the origin
  `imported`, no lines, the amounts of the list as its frozen totals and the PDF archived with its
  SHA-256 like the PDF of an invoice written here (ADR 0007). It is never rendered: `html` refuses it,
  `pdf` returns the stored original and refuses to render one when there is none.
- **Further files of the number are attachments** (`document_attachments`): reminders, corrected copies
  and versions the old program kept next to the invoice. They are only ever added; a trigger refuses
  changes and deletions and checks the content against its hash, as for the PDF.
- **Files are found by the invoice number in their name**, anywhere in it, also without the number's
  letters ("R20150001" in "Rechnung 20150001.pdf") and with other separators – but not where other
  letters stand instead ("GS-100.pdf" is no file of "RE-100"). Of several files the one with nothing
  else in its name is the invoice, the others are attachments; a file named as a reminder or copy
  ("Mahnung", "Korrektur", "Kopie" …) never becomes the invoice, which then has no PDF yet. Copies
  with the same content count once, and a file belongs to one invoice only. When the list has no mapping yet, the column whose values name the most files
  becomes the number column: programs often export a counter as "Rechnungsnummer" and the number in
  the title.
- **Customers** are found by number, else by name (ignoring case, spaces and punctuation). A number
  whose customer has a clearly different name is not taken (the old program's numbers may be
  Rhinvoice's numbers of other customers); a renamed customer ("Farben Kobold KG" → "FarbenKobold
  GmbH") still is. Unknown ones are created and archived, "customer since" the date of their first
  invoice, so that former customers do not crowd the lists.
- **Numbers that exist are skipped**: an issued invoice never changes, also not by importing it again.
  Afterwards the invoice sequence moves to the next free number, and allocating a document number
  passes over numbers in use: imported numbers ahead of the counter are never given twice.
- **What was paid becomes one payment on the due date** (at the latest the day of the import): the
  lists say what is open, not when it was paid. Without an open amount an invoice counts as paid. These payments are left out of the average
  days to pay; the import is left out of the recent activities.
- **What needs lines is refused** for imported invoices: duplicating, cancelling (a cancellation reverses
  lines), recurring plans and e-invoices. Payments, reminders and mails work as for any invoice.
- A missing PDF can be added on the invoice afterwards, once; further PDFs become attachments. Each
  addition is confirmed first, since it cannot be undone, and logged in the history.
- A row is saved whole or not at all: everything, also the attachments' names, is checked before the
  first write. The test run matches and checks the files without storing them.

## Consequences
- The import takes the list and the files in one request (folder, single PDFs or ZIP files, at most
  200 MB, 1000 files per request from the browser; more as ZIP). All ZIP files of a request together
  unpack to at most 500 MB and 10'000 entries, each PDF at most 20 MB; the public demo takes small
  requests only. PDFs are stored in the database and
  go into every backup with it.
- Imported invoices show their PDF instead of the paper preview, are marked "Taken over" in lists and
  count in the dashboard's revenue by their date.
- Old invoices are not cancelled in Rhinvoice. A correction of one is a new invoice or a cancellation
  written here by hand.
- A file whose name does not contain the number is not matched; the test run lists such files, and the
  PDF can be added on the invoice.
