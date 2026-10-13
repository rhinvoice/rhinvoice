# 0020 – Writing off invoices that will not be paid

- Status: accepted
- Date: 2026-10-13

## Context
Some invoices are never paid: the customer was dissolved, the claim is time-barred or collecting it
costs more than it brings. Such an invoice stayed overdue forever. Cancelling it is wrong, because
the invoice was correct and a cancellation revokes it with a document to the customer (DE § 31
Abs. 5 UStDV, AT § 11 Abs. 12 UStG, CH/LI Art. 27 Abs. 4 MWSTG); invoices taken over from another
program cannot be cancelled at all (ADR 0019). Marking it as paid is wrong too: no money came in.

## Decision
- **A write-off is a movement on the invoice, like a payment, not a document.** The invoice stays as
  issued (ADR 0005), nothing goes to the customer, no number is used. It gets the stored status
  `written_off`: not open, never overdue, not reminded, not cancellable.
- **Its own table** (`document_write_offs`, at most one per invoice, recorded or taken back, never
  edited), not a kind of payment: everything that sums payments would have to tell the kinds apart,
  and one forgotten place would count a loss as money received.
- **The whole open rest is written off**, never a part of it. After a part payment or an insolvency
  dividend the payment is recorded first.
- **Date:** from the invoice date up to today. Today is suggested; the end of the invoice year is
  offered, for old invoices and for companies that account for the tax on receipt, where the date
  has no tax effect.
- **A payment after the write-off** is recorded as usual, up to the written-off amount. The
  write-off stays in its year; the payment counts as recovered in the year it came in (DE § 17
  Abs. 2 Nr. 1 Satz 2 UStG, AT § 16 Abs. 3 UStG correct the tax again in that period). Paid in
  full, the invoice is `paid`. Recoveries are the payments recorded after the write-off; such a
  payment is not dated before the write-off, and a write-off is refused while a payment lies ahead
  of the clock, so that the two are never confused.
- **Taking it back** (a mistake) reopens the rest and is logged, also after the invoice was paid
  in full (it then stays paid). Payments from before the write-off cannot be removed while it
  stands: it names the rest after them. An invoice with a write-off is not cancelled; the write-off
  is taken back first.
- **Tax is stated, not corrected.** Whether the tax is corrected depends on how the company accounts
  for it (agreed or received consideration), which Rhinvoice does not know. The report shows written
  off, recovered, loss, net and the tax contained per year and currency; the tax is spread evenly
  over the invoice total.
- **Per country only words differ**, not the calculation: `CountryTerms.bad_debts`
  ("Debitorenverluste" in CH/LI, "Forderungsausfälle" in DE/AT) and `CountryTerms.write_off_hint`
  with the country's rule and its legal basis (CH/LI Art. 41 MWSTG, DE § 17 Abs. 2 Nr. 1 UStG,
  AT § 16 Abs. 3 Z 1 UStG).

## Consequences
- The dashboard counts what was written off neither as open nor as paid; revenue stays what was
  invoiced. Written-off invoices are left out of the average days to pay, also when paid later.
- The trigger `rhinvoice_protect_document` is unchanged: status and the list values were never
  frozen.
- No accounting method setting, no VAT return, no bulk write-off. A discount agreed afterwards
  remains a cancellation and a new invoice.
