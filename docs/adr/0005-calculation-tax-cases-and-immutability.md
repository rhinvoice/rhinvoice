# 0005 – Calculation, tax cases and immutability of documents

- Status: accepted
- Date: 2026-10-10

## Context
CLAUDE.md §6 defines the order of the calculation (line → line discount → overall discount → tax per
rate → rounding only on the final amount) and requires issued documents to be immutable
(GoBD, OR 958f, BAO). Still open were the exact rounding, the distribution of an overall discount across several
tax rates, the choice of tax rate when rates change, and the technical safeguarding of
immutability.

## Decision

### Calculation (`domain/document/calculation.py`)
- Money is `Decimal`, never `float`. Rounding is commercial (`ROUND_HALF_UP`) in a local
  `Decimal` context with 60 digits, so that intermediate results are not truncated.
- **Line amount** = quantity × unit price × (1 − line discount), rounded to the smallest unit of the
  currency (0.01). This way the printed line amounts add up to the total.
- **Groups**: lines are grouped by (UNCL5305 tax category, rate), in the order of their
  first occurrence.
- **Overall discount as a percentage** is calculated and rounded per group. **Overall discount as an amount** is
  distributed proportionally across the groups; the rounding remainder goes to the group with the largest amount, so that the
  sum equals the discount exactly. An amount discount larger than the subtotal is rejected.
- **Tax** is calculated and rounded per group on the discounted group total (net: total × rate;
  gross: total × rate / (100 + rate), net = gross − tax). This matches the presentation "MWST 8.1 %
  on CHF …" on the invoice.
- **5-centime rounding (Rappenrundung)** (CHF to 0.05, can be disabled per company) applies only to the final amount and is shown as a separate
  "Rounding" line. Tax amounts stay rounded to 0.01 only.
- Property tests (hypothesis) ensure: sum of lines = subtotal, net + tax = gross,
  gross + rounding = total, rounding at most half a rounding step, tax per group at most
  half a centime/cent away from the exact value, order of lines has no effect, and cancellation = −invoice
  for every amount.

### Tax rates and tax cases
- Rates are dated data per country (`domain/tax/rates.py`, sources in the code). The rate that applies is the one on the
  **date of supply** (end of the service period, otherwise its start, otherwise the invoice date).
- Drafts without a date of supply use the rate valid today (not the rate on the day they were created).
  On **issuing**, the rate of every line is frozen and stored with the document; later
  rate changes do not apply retroactively.
- On issuing, the tax case is **determined anew** from the current master data (the customer may have changed since
  the draft was saved), unless it was chosen manually. Reverse charge is only issued with the
  customer's UID / USt-IdNr.
- The tax case (domestic, reverse charge, export, small business, exempt) is determined from the company's country, the customer's country,
  B2B/B2C, UID and tax exemption. A manual choice is possible and is logged with a reason as the
  event `tax_overridden`. Uncertain cases are described in `OPEN_QUESTIONS.md`; in each case the
  conservative variant is implemented.
- A cancellation invoice is never "overdue": it cancels its invoice and is due on its issue date.

### Immutability
- Numbers are assigned only on issuing, in the same database commit as the issuing, under a
  row lock on the number sequence (`SELECT … FOR UPDATE`). Aborted transactions do not consume a
  number; a unique index prevents duplicates even if the code has bugs.
- On issuing, **snapshots** of company, customer and bank account as well as the totals are stored as JSONB.
  Later changes to master data do not change issued documents.
- **Database triggers** (`rhinvoice_protect_document`, `rhinvoice_protect_document_lines`) forbid
  content changes and the deletion of documents that are no longer editable, and of their lines. Only
  status changes (payments, cancellation, quote accepted/declined), setting the PDF hash once, and
  references to follow-up documents remain allowed. The protection thus also holds for bugs in the application code and for direct
  SQL access.
- Corrections are made exclusively via a **cancellation invoice** with its own number. It takes over the
  invoice's frozen rates, sender, recipient and rounding and negates the quantities; on cancellation it is
  checked that its total equals the negated invoice total exactly. Drafts may be deleted,
  issued documents never.
- **Date and number:** the document date must not be in the future and not before the last issued
  document of the same type. The number (`{YYYY}` etc.) follows the document date. This way
  numbers and dates increase together.
- Invoices with a total ≤ 0 are not issued; credit notes arise only from cancellation.
- A quote is converted into an invoice at most once (only when sent or accepted) and refers to
  it. If the invoice draft is deleted, the quote is free again.
- The event history is **append-only** at the database level; payments can be recorded or (logged)
  removed, but not modified.

### Payments
- Payments are positive, have at most two decimal places and must not be in the future.
- **Overpayments** are not recorded: a payment must not exceed the open amount. The excess
  (e.g. a double payment) is refunded outside of Rhinvoice or represented later as a credit balance
  (extension stage 8). This way "paid" stays unambiguous and the open amount is never negative.
- Every change creates an event (created, issued, payment recorded/removed, cancelled …) with a
  timestamp. The history is visible in the document.

## Consequences
- Totals are calculated exclusively in the backend. The frontend shows live totals via
  `POST /api/documents/preview` and never calculates with money amounts itself.
- For centime/cent differences compared with other programs, rounding per group
  is the first explanation (see `OPEN_QUESTIONS.md`, item 4).
- A refund after cancelling an invoice that was already paid is not represented yet (extension stage 8).
