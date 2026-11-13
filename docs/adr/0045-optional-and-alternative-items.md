# 0045 – Optional and alternative items

- Status: accepted
- Date: 2026-11-13

## Context
A quote often offers more than the customer will order: an add-on on top, or a second package
instead of the first (#87, discussion #66). Until now each item of a quote counted into its
total, so such offers were written as text or as a second quote.

## Decision
- **A line of a quote counts into the total or not** (`DocumentLine.in_total`): `yes` (the
  default), `optional` (offered on top) or `alternative` (offered instead of another item,
  `alternative_to` naming it). The replaced item is an item of the same quote that counts
  itself; an alternative to an alternative or an option is refused
  (`alternative_target_invalid`). Text lines always count; they have no amount to leave out.
- **Only quotes** offer such items. Invoices, cancellations and recurring plans refuse them
  (`in_total_quotes_only`): what is invoiced is owed, and the e-invoice stays as it is.
- **The totals leave them out**: VAT groups, document discount, net, tax, pass-through sum,
  cash rounding and so the dashboard and every open amount. Each keeps its own line amount, for
  the quote to show. The totals JSON keeps its shape; whether a line counts is read from the
  line itself.
- **In the editor** (variant 1A chosen by Kadir) the opened item of a quote has *In total*:
  *Yes*, *Optional* or *Alternative to item N*, offering every other item that counts. Closed
  items show a tag and their amount muted. When the replaced item is removed or stops counting,
  the alternative becomes optional; the server refuses an invalid reference anyway. The API
  names the replaced item by its index in `lines`, since line ids are new on every save.
- **In the PDF** (variant 2A) the items stay in place, muted, with a small tag ("Optional",
  "Alternative zu Pos. 2") and the amount in brackets; a note below the totals says that such
  amounts are not included. Without printed position numbers (or for a pass-through item) the
  tag reads "Alternative" alone, as the reader could not find the number.
- **Turning the quote into an invoice** (variant 3B): only when the quote has such items, a
  dialog lists all items with a checkbox, those in the total ticked, and the total of the
  choice. `POST /documents/{id}/convert` takes `line_ids`; without them, the items in the total.
  The chosen items become ordinary lines of the invoice, text lines always come along; at least
  one item is chosen (`no_positions_chosen`), and only items of the quote
  (`line_not_in_document`). A duplicate of a quote keeps its options; any other copy into an
  invoice takes the items in the total.
- **Migration 0028** adds `in_total` (default `yes`) and `alternative_to` to the lines with a
  check that exactly the alternatives name an item. The trigger of the lines keeps issued
  quotes frozen, the new columns included. A downgrade stops while any line does not count.

## Consequences
- A quote with options needs no second quote and no workaround in text lines.
- The invoice of such a quote is an ordinary invoice: nothing changes for payments, reminders,
  e-invoices or the export.
- Themes written before keep working: the new fields of a printed line have defaults, and the
  bracketed amount is part of the amount itself.
