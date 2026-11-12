# 0042 – The details top right

- Status: accepted
- Date: 2026-11-11

## Context
Next to the address, documents print a fixed list: number, customer number, date, due date, date
of supply and the reference. Customers ask for more: a project, their purchase order, a cost
centre (#62). Others want less, e.g. no date of supply when the positions state it (#60). Several
of these details have a business term of their own in the e-invoice (EN 16931), so printing them
only in the PDF would leave the e-invoice short of what the customer's accounting looks for.

## Decision
- **The print layout lists the details in order** (`PrintLayout.info_block`), one entry each:
  - **Rows** that Rhinvoice fills in: number, customer number, date, due date, date of supply,
    reference. Each is listed once and can be moved. Number and date are always shown; the
    others can be hidden.
  - **Reference fields** with a value per document that also go into the e-invoice: project
    (BT-11), contract (BT-12), purchase order (BT-13), sales order (BT-14), delivery note
    (BT-16), tender or lot (BT-17), invoiced object (BT-18) and cost centre (BT-19). BT-15
    (receiving advice) is left out: an invoicing program for small businesses rarely gets one.
  - **Own fields** with a name of the user's choosing, PDF only. Their key ("custom-" and 8 hex
    digits) stays when the name changes, so the values stay with it. At most ten.
  - The customer's VAT ID stays automatic after the list: reverse charge and intra-Community
    supplies require it.
- **The default is the old list**, so no update changes how documents look. Layouts and issued
  documents saved before keep it.
- **The date of supply can be hidden in the PDF**, with a warning: it is mandatory (§ 14 Abs. 4
  Nr. 6 UStG, § 11 Abs. 1 Z 3 lit. d UStG AT) and may only be left out when the positions state
  it. The e-invoice always keeps it (BT-72).
- **Values belong to the document** (`DraftContent.fields`), up to 100 characters each:
  - The editor asks for everything printed top right in one place, the card *Dates*: the
    service period, the reference and the fields of the document's layout, for invoices, quotes
    and recurring plans alike (plans set the service period themselves). A row the layout hides
    stays to be filled in, with a note that only the e-invoice carries it. Values of fields
    removed from the layout stay with the document unseen and come back with their field.
  - A value prints, and goes into the e-invoice, only while the document's layout lists its
    field. Issued documents use the layout frozen with them, so PDF and e-invoice agree.
  - Issuing freezes the values: the column is in the document trigger's frozen columns.
  - Duplicates, quotes turned into invoices, cancellations and recurring plans carry them.
- **BT-13 and the reference.** The purchase order field fills BT-13. Without it, the reference is
  BT-10, or BT-13 when a German authority's Leitweg-ID takes BT-10 (ADR 0013). When the
  Leitweg-ID and a purchase order leave no place for the reference, it goes into a note (BT-22)
  as "Your reference: …", so nothing printed is missing from the e-invoice.
- **CII.** The references follow the parties in the header trade agreement in the schema's order
  (BT-14, BT-13, BT-12, BT-17 and BT-18 as additional documents with type codes 50 and 130,
  BT-11 with the fixed name "Project reference"), BT-16 follows the delivery event, BT-19 ends
  the settlement. A sample with every field passes KoSIT (EN 16931 and XRechnung) and Mustang.

## Consequences
- Customers who want a project or cost centre get it in the PDF and in the e-invoice without
  misusing the subject or the reference.
- One more list to keep in order in the print layout; its rules are checked in the domain.
- With several print templates per customer (#48), each template brings its own list.
