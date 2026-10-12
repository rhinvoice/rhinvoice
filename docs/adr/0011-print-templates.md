# 0011 – Print templates

- Status: accepted
- Date: 2026-10-11

## Context
It should be possible to design invoices without knowing HTML: pick a ready-made template and
adjust it (logo, font, header, footer, all bank accounts). A free-form editor with drag-and-drop
would put the fixed positions at risk (address field in the window envelope according to DIN 5008 / SN 010130, Swiss
QR payment part).

## Decision
- **Three templates** (Classic, Modern, Plain) as CSS variants of the same page, plus a few
  switches: logo left/right and small/medium/large, sans-serif/serif font (Inter, Source
  Serif 4, both embedded), sender line (hidden, not removed: the address stays in the
  window), contact details in the header, line numbers, bank accounts in the footer (all or only
  the one for the invoice currency; accounts of one bank in a short column).
- **Positions stay fixed:** header with fixed height, address field, payment part on a separate page.
- **Issued documents are immutable, including their appearance:** the layout and bank accounts of the day
  belong to the snapshot taken on issuing. Older documents (from before this version) use the current ones.
- **Preview** before saving, using the latest invoice (otherwise a sample invoice).
- **Custom templates** remain possible via the theme folder (`layout.html.j2`, `document.html.j2`,
  `reminder.html.j2`, `document.css`).

## Consequences
- The logo is not part of the snapshot: a new logo appears in the HTML view of older
  documents; the archived PDF remains authoritative.
