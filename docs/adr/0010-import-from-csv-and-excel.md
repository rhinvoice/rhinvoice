# 0010 – Import from CSV and Excel

- Status: accepted
- Date: 2026-10-11

## Context
CLAUDE.md §8 requires an import of customers and articles from CSV and Excel with column mapping,
preview, dry run, duplicate strategy, character encoding detection and saved templates.
Earlier programs often export in the old Excel format (.xls) or as CSV in Windows-1252 with
semicolons.

## Decision
- **Reading:** the file type follows from the content (XLSX = ZIP, XLS = OLE), not from the extension. CSV
  is read as UTF-8 (also UTF-16 with BOM) or Windows-1252, and the delimiter is detected.
  Limits: 5 MB, 10'000 rows, 100 columns; every cell is looked at once, unpacked XLSX
  at most 50 MB (against crafted files).
- **Dry run = import without commit:** the same code runs in a transaction that is not committed
  in a dry run. What the dry run reports is what the import does (including the numbers).
- **Mapping:** columns are recognised by common names (synonyms, ignoring case,
  umlauts, punctuation). If a column is missing without which no row can be matched (number
  or name), the dry run returns the columns instead of rows, so that they can be mapped by hand.
- **Values:** amounts are parsed strictly (Swiss, German and English notation; «1.500» depending on the company's
  country), countries from names and codes, units from codes and labels, tax rates from names
  or percentages. Anything unclear is reported as an error of the row, never guessed.
- **Duplicates:** same number, otherwise same name (customers: and postal code). Skip, update
  (empty cells change nothing; street and house number together) or create new (number taken →
  next free one). Existing records are loaded once instead of queried per row.
- **Faulty rows** are reported (field, reason, value) and not imported; they do not consume
  a number. The report can be downloaded as CSV (without formulas, OWASP CSV Injection).
- **Templates** store the mapping as column names per target (customers, articles). There is no
  bundled template for any particular program; recognition via common names covers the
  usual exports.

## Consequences
- Very large imports (10'000 rows) run synchronously in one request; behind a reverse proxy
  with a short timeout this can get tight.
- Invoices are not imported (old invoices remain archived in the previous program).
