# 0027 – Leitweg-ID as a fixed buyer reference of the customer

- Status: accepted
- Date: 2026-10-16

## Context
The XRechnung needs a buyer reference (BT-10, BR-DE-15). With [ADR 0013](0013-e-invoices.md) it
came only from the invoice's *reference* field. A German authority keeps its Leitweg-ID for
years, so it had to be typed into every invoice, and users did not find out that the
Leitweg-ID belongs there. The problem only showed after issuing, when the invoice was frozen.

## Decision
- The customer has an optional **buyer reference** ("Leitweg-ID oder feste Käuferreferenz").
  If set, it is the buyer reference of every e-invoice to that customer (XRechnung and
  ZUGFeRD); otherwise the invoice's reference is, as before. Both empty: the XRechnung
  lacks `buyer_reference_missing`.
- The value comes from the **customer snapshot** of the issued invoice, so later changes of the
  customer do not change issued e-invoices. Snapshots written before have no such key and
  read as empty.
- The field is shown, and applies, **only for customers in Germany**: the XRechnung is the
  e-invoice of German authorities. The value is kept when the country changes, so moving a
  customer back and forth loses nothing; a value kept on a customer elsewhere does nothing.
- For customers in Germany, the dialog before issuing lists what the **XRechnung** lacks, next
  to the problems of the embedded ZUGFeRD invoice. It is a warning; issuing stays possible.
  Other customers see no XRechnung warning.

## Consequences
- Authorities are set up once; invoices to companies keep using the per-order reference.
- The draft preview asks for the XRechnung problems of German customers in addition to the
  ZUGFeRD problems (one more e-invoice check per preview for them).
- A buyer reference typed on a customer abroad is silently ignored; the form hides it there.
