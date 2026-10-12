# 0006 – Text templates and legal notices

- Status: accepted
- Date: 2026-10-11

## Context
Recurring texts (introduction, payment terms, closing text) should not have to be typed for every invoice
(CLAUDE.md §5 "TextTemplate", a request from testing v0.3.0). The tax notice for reverse charge
("Übergang der Steuerschuld auf den Leistungsempfänger", transfer of tax liability to the recipient) is required by the tax advisor and must not be
forgotten. Issued documents are immutable (ADR 0005).

## Decision
- **Text templates** (`domain/text/template.py`): kind (introduction, payment, closing), document type
  (invoice, quote), language, name, text, "default" and order. Default templates are inserted into new
  documents (joined with line breaks, in their order) and remain editable there.
  Migration 0006 creates German and English suggestions.
- **Placeholders** `{nummer} {datum} {faellig} {kunde} {betrag} {waehrung}` (German names as in the product):
  the text is stored with placeholders; they are replaced only when displaying and printing, from the
  document's data. For issued documents this data is frozen, and so is the result. Unknown
  placeholders are rejected when saving a template (`unknown_placeholder`), so that typos such as
  `{faelig}` do not end up on invoices.
- **Payment terms** are a separate field of the document (`payment_text`), printed after the totals.
- **Legal notices** (`domain/text/notice.py`) follow automatically from the tax case (reverse
  charge, export, small business, tax-exempt), with wording per company country and language, sources in the code.
  The company can replace the wording in the settings; an empty text restores the built-in one.
  On issuing, the wording valid at that time is frozen in the snapshot (also for the cancellation invoice).
  Drafts show the current wording.
- **CH/LI → EU business with UID** is reverse charge instead of export (place of supply at the recipient,
  Art. 8 Abs. 1 MWSTG; tax liability of the recipient in the EU country). Supplies of goods are not distinguished;
  the manual override remains for those (OPEN_QUESTIONS 8).

## Consequences
- New documents are complete without typing; the notice for the tax case is never missing.
- Wording changed later does not change issued documents.
- The invoice template (HTML/PDF) only needs document data, placeholder replacement and the notice.
