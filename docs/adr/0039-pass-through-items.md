# 0039 – Pass-through items

- Status: accepted
- Date: 2026-10-30

## Context
Fiduciaries, notaries, agencies and craftspeople pay fees for their customers (commercial
register, land register, customs, authorities) and charge them on (issue #46). Paid "in the
name and for the account" of the customer, such amounts are not part of the taxable amount:
DE § 10 Abs. 1 Satz 4 UStG, AT § 4 Abs. 3 UStG 1994, CH and LI Art. 24 Abs. 6 lit. b MWSTG,
in CH and LI only "sofern sie diese gesondert ausweist". Until now a user could only mark such
a line as exempt, which mixes it with exempt supplies in the VAT groups, lets the document
discount reduce it and counts it as revenue.

## Decision
- **A tax category of its own.** `TaxCategory.PASS_THROUGH` ("pass_through") next to the
  rates, *zero* and *exempt*, so the existing "Steuer" select of a line and of an article
  offers it as "Durchlaufender Posten (ohne MWST)" or "(ohne USt.)", in the country's tax
  word. A separate flag was rejected: it would combine with every category, of which only one
  makes sense. *Exempt* ("Von der Steuer ausgenommen") stays as it is. The column grows from
  10 to 20 characters (migration 0022).
- **Only with the customer's name.** When chosen, the select says "Nur wenn die
  Fremdrechnung auf den Namen Ihres Kunden lautet." Purchases in one's own name are normal
  taxable lines. Rhinvoice gives no tax advice; the user decides.
- **Calculation.** A pass-through line has no VAT and belongs to no VAT group, whatever the
  document's treatment (domestic, reverse charge, export, small business, exempt customer)
  and whether it is goods or a service; it has no treatment and adds no notice. The document
  discount is spread over the VAT groups only, never over pass-through lines; an amount
  discount may not exceed the other lines. `Totals.pass_through` holds their sum; `net`, `tax`
  and `subtotal` leave it out, `gross` (before cash rounding) and the payable `total` include
  it, so QR-bill, EPC QR code, payments, open amounts and reminders do. The Swiss 5-centime
  rounding applies to the final total only. Totals frozen before (JSON without the field) read
  as zero. Property tests pin: total = taxed part + pass-through sum (rounded at the end), and
  adding pass-through lines changes neither the groups nor the discount.
- **Printed block.** Pass-through lines leave the positions table and follow the tax lines,
  before the rounding and the total, under "Durchlaufende Posten (im Namen und auf Rechnung des
  Kunden bezahlt)" (DE, with EN, FR, IT), each with its description and amount (quantity × price
  and line discount in brackets when not 1). This is the separate statement the MWSTG asks
  for. Documents without such lines print exactly as before; positions keep their numbers. In
  the editor's preview a click on an item opens it like a position. The in-table variant waits
  for named print templates (no update changes the look of invoices).
- **E-invoice.** EN 16931 has no category for pass-through amounts; "O" may not stand next to
  other categories (BR-O-11). They are exempt, category **E**, with the exemption reason code
  **VATEX-EU-79-C** ("Exemptions relating to repayment of expenditures", Art. 79 lit. c VAT
  Directive) and the block's title as reason text, in a VAT breakdown of their own, numbered
  after the printed positions. EN 16931 allows one breakdown per category and rate (BR-E-08):
  next to exempt lines of another reason both share it with both reason texts and no code
  (BT-121 holds one); outside VAT ("O", Swiss small businesses without VAT number) the lines
  are "O" and join that breakdown. Samples for Germany (19 % plus pass-through, with a
  discount; with exempt lines) and Switzerland (two rates and rounding; cancellation; small
  business) pass KoSIT and Mustang in `make einvoice-qa`.
- **Revenue.** Not revenue: the dashboard's revenue, year to date and best customers use the
  stored net amount, which leaves them out. Open, overdue and expected amounts include them:
  the customer owes them.
- **Export (ADR 0038).** A column "Durchlaufende Posten" between *Steuer* and *Brutto*, in the
  list and in the sums, only when the export holds such amounts (like the rate columns).
  *Netto* and *Steuer* leave them out, *Brutto* includes them.
- **Import.** The tax column of an article import reads "durchlaufend", "durchlaufender Posten",
  "pass-through".

## Consequences
- One more choice in the tax select; nothing else appears unless a line uses it.
- The third-party invoice usually goes along: see ADR 0040 for attachments.
- Not taken from primary sources (OPEN_QUESTIONS 19): that E with VATEX-EU-79-C is the right
  e-invoice mapping (practice, no KoSIT statement), and the ESTV practice. A professional
  should review it; the validators accept it.
