# 0016 – Recurring invoices

- Status: accepted
- Date: 2026-10-12

## Context
Hosting, maintenance contracts, subscriptions and flat fees are invoiced with the same content every
month, quarter or year. Writing them by hand is tedious and easy to forget.

## Decision
- **A plan per repeated invoice:** customer, the invoice's content as a template (positions, texts,
  currency, prices, discount), an interval (monthly, quarterly, half-yearly, yearly), the day of the
  first invoice (today or later), an optional last day, and what happens on the day: create a draft,
  issue, or issue and send by mail (ADR 0015). Optionally the period an invoice covers is its service
  period.
- **Dates are counted from the first day** (`start + n × interval`), so a plan starting on the 31st
  invoices on the last day of shorter months and returns to the 31st; periods follow each other without
  gap or overlap (property test).
- **The plan editor is the invoice editor** with a settings card on top and without dates, tax choice
  and issuing; the live preview shows the next invoice. An issued invoice can be made recurring.
- **The web server writes due invoices itself**, in a background thread of `rhinvoice serve`: a minute
  after the start and then every ten minutes (`RHINVOICE_RECURRING_INTERVAL`, can be switched off with
  `RHINVOICE_RECURRING=false`). `rhinvoice recurring` does it at once, e.g. from cron. No worker
  container: existing installations get the feature with the image update.
- **Each period is written once.** A run claims the period in the database (unique per plan and
  period, with the plan row locked) and moves the plan on in the same transaction; only then is the
  invoice written. Several server processes, a restart or a crash never write a period twice; a crash
  in between leaves the run marked as interrupted.
- **Missed periods are caught up** (server off for a while): every period gets its invoice, dated the day
  it is written, with its own service period; at most 24 per plan and run. Periods missed while a plan
  was paused are skipped.
- **Problems are shown, not hidden:** an invoice that cannot be issued (e.g. no bank account) stays a
  draft, one that cannot be sent (no customer address, mail server refuses) stays issued; the plan shows
  the last runs with the reason and links to the invoices, and is marked "Problem" in the list.

## Consequences
- Prices and texts are those of the plan; changing an article does not change plans.
- Invoices are dated the day they are written, also when caught up after a downtime.
- Deleting a plan keeps the invoices it wrote.
- Mails sent by a plan carry the PDF with its embedded e-invoice, not a separate XRechnung; German
  authorities that need XRechnung get it sent by hand from the invoice.
- `rhinvoice recurring` exits with 1 when an invoice needs attention, for cron and monitoring.
