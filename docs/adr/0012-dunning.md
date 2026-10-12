# 0012 – Dunning

- Status: accepted
- Date: 2026-10-11

## Context
Overdue invoices should be dunned with little effort: payment reminder, then dunning letters,
with a new deadline and, if desired, a fee, traceable in the invoice's history.

## Decision
- **Three levels:** payment reminder, 1st dunning letter, 2nd dunning letter. Each becomes due a configurable number of
  days after the last deadline (the first after the invoice's due date) and sets a new
  deadline. A level may also be written before its date; further steps (debt enforcement (Betreibung),
  debt collection, court dunning procedure) are out of scope.
- **Reminders are not documents with a number:** a reminder belongs to the invoice, records the open
  amount and the fee, and appears in the invoice's history. There is one reminder per invoice and level
  (database uniqueness).
- **Fees without tax** (damages), in the invoice's currency, in steps of 0.05
  (5-centime rounding (Rappenrundung) of the payment codes), **default 0**: depending on the country, a fee requires an agreement or
  proof of the costs. Default interest is not calculated.
- **No accidental reminders:** the request names the level that was seen (a second click
  writes nothing); a level before its date only deliberately (`early`, with confirmation in the UI).
- **Reproducible:** the level's text is stored with the reminder; the reminder prints as
  written, even if the settings change later. Header, address and accounts are those from
  issuing the invoice (the payment reference belongs to its account).
- **On paper** the invoice's page (header, address, footer in the layout from issuing) with the level's
  text, open amount, fee and total; the QR-bill or GiroCode requests the total and
  carries the invoice's reference, so that the payment can be matched. Reminder PDFs are not
  archived (the invoice is the accounting record).

## Consequences
- A payment of open amount plus fee exceeds the invoice's open amount; the
  fee is booked outside (the invoice is marked as paid with the open amount).
