# Moving from another program

Rhinvoice takes over customers, articles and old invoices from the program you used before. Every
import starts with a test run that changes nothing: you see each row with what would happen to it,
and only **Import** saves. Files: CSV (UTF-8 or Windows-1252), Excel `.xlsx` and `.xls`.

1. **Customers** (*Customers → Import*): number, name, address, contact, VAT number, customer
   since … Columns are recognised by their names; anything else can be mapped by hand and saved as a
   template.
2. **Articles** (*Articles → Import*): number, name, unit, prices, VAT rate (also former rates such as
   the Swiss 7.7 % or 8 %).
3. **Invoices** (*Invoices → Import*), last, so that they find their customers.

## Old invoices

Old invoices come over as what they were: issued, locked invoices with their number, date, customer
and amounts, and with their **original PDF**. Rhinvoice does not recalculate or redraw them, so the
invoice you keep is the one your customer got (ten years: CH OR 958f, DE § 147 AO, AT § 132 BAO).
They appear in the invoice list (marked *Taken over*), in the customer's history, in search and in
the revenue of their year; open ones can be marked as paid like any other.

You need:

- **A list of the invoices**, exported from the old program. Needed columns: invoice number, date,
  total and customer number or name. Used when present: due date, net amount or tax amount, open
  amount, currency, subject and the customer's address (for customers Rhinvoice does not know yet).
- **The PDF files**, as a folder (with subfolders), single files or ZIP files. Rhinvoice looks for the
  invoice number in the file name, anywhere in it: `Rechnung R20150001.pdf`, `R2015-0001.pdf`,
  `2015/20150001_korrektur.pdf`. Of several files with the same number the one with nothing else in its
  name is the invoice; the others (reminders, corrected copies, versions) are kept with it as
  attachments. A file named as a reminder or copy ("Mahnung", "Korrektur", "Kopie" …) is never taken
  as the invoice itself. Identical copies are kept once. Pictures and other files in the folder are
  left out.

What happens:

- Some programs export a counter as "invoice number" and the real number in the title
  ("Rechnung R20150001"). Rhinvoice takes the column whose values match the file names.
- Customers are found by number, else by name. A number that belongs to a customer with a clearly
  different name is not used. Customers it does not know are created and **archived**, so that
  former customers do not crowd your lists.
- An invoice without an open amount counts as paid. What was paid becomes one payment on the due
  date, since the old program's payment dates are not in the list.
- Numbers that exist already are skipped: an issued invoice never changes, not even by importing it
  again. You can import the same list twice without harm, e.g. a second time with the PDFs.
- Afterwards the invoice number sequence continues with the next free number, and numbers taken by
  imported invoices are passed over later on; the result says which number the next invoice gets.
- Files that belong to no invoice of the list are listed in the test run. An invoice without PDF can
  get it later on its own page (*Add PDF*); further files become attachments. Rhinvoice asks before,
  since neither can be replaced or removed afterwards.

Limits per import: the list 5 MB and 10'000 rows; the PDFs 20 MB each and 200 MB together. A browser
sends at most 1000 files at once: pack larger folders as ZIP, or import year by year.

Imported invoices cannot be duplicated, cancelled or sent as e-invoices: they consist of their PDF.
The PDFs are stored in the database and are part of every backup ([backup.md](backup.md)). Keep the
old program's export until you have checked the import.
