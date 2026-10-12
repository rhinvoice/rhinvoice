# 0014 – Goods and services

- Status: accepted
- Date: 2026-10-12

## Context
Until now every position was treated as a service. For services, the place of supply follows the
recipient (Art. 44 VAT Directive, Art. 8 MWSTG): to businesses abroad without domestic VAT, with
reverse charge within the EU. Goods follow other rules when they cross a border:

- within the EU, to a business with a VAT number: **tax-free intra-Community supply**
  (Art. 138 VAT Directive; § 4 Nr. 1 lit. b and § 6a UStG DE; Art. 6 Abs. 1 and Art. 7 UStG AT),
  with both VAT IDs on the invoice (§ 14a Abs. 3 UStG DE), proof of arrival and the EC Sales List;
- leaving the VAT area (from DE/AT out of the EU, from CH/LI abroad): **tax-free export delivery**,
  also to private customers, with proof of export (§ 4 Nr. 1 lit. a and § 6 UStG DE; § 6 Abs. 1 Z 1
  and § 7 UStG AT; Art. 23 Abs. 2 Ziff. 1 MWSTG). From Switzerland there is no reverse charge for goods:
  the customer pays import VAT.

## Decision
- **Articles and positions are a service or goods** (default: service, so every existing document
  stays as it was). A position takes the kind of its article and can be changed in the editor; imports
  read it from a column such as "Art".
- **The document's treatment stays the treatment of its services.** Goods positions get a treatment of
  their own when the draft is saved and again when it is issued, from the place they are delivered to
  (the customer's delivery address, else the address): staying in the company's VAT area they are taxed
  at home, to an EU business with a VAT number they are an intra-Community supply (DE/AT), leaving the
  EU (DE/AT) or Switzerland and Liechtenstein they are an export delivery, to private customers in other
  EU countries they keep domestic VAT. A treatment chosen by hand also applies to goods, in their form:
  reverse charge across a border becomes an intra-Community supply or an export, a domestic reverse
  charge (e.g. § 13b Abs. 2 Nr. 7 UStG) stays one, an export is an export delivery.
  Intra-Community supply and export delivery are never chosen for a whole document.
- **Mixed documents** group VAT per treatment as well as per rate: an Austrian invoice to a private
  customer in Switzerland charges 20 % on the service and 0 % on the goods.
- **Notices per treatment:** each treatment of the positions puts its notice on the document, both can
  be worded in the settings and both are frozen when issuing (the goods notice next to the existing one
  in the snapshot).
- **Issuing an intra-Community supply needs the VAT IDs of the company and of the customer.**
- **E-invoices:** goods within the EU are category K (VATEX-EU-IC) with the delivery address as
  deliver-to (BR-IC-12), exports are G; the exemption reason of each category is the notice of its
  treatments. Services to businesses outside the EU are strictly "not subject" (O), but EN 16931 allows
  O only alone on an invoice (BR-O-11 to 14); they stay G, so a service and a goods export share one
  group with both notices.
- Print themes written for earlier versions keep working: they get all notices joined as `notice`.
- The editor reminds of the proof of export or of arrival when goods are tax-free.

## Consequences
- Distance sales of goods to private customers in other EU countries keep domestic VAT. Above the
  EU-wide threshold of EUR 10'000 a year the VAT of the customer's country applies (OSS); Rhinvoice does
  not track the threshold (OPEN_QUESTIONS).
- Places inside the EU but outside its VAT area (Canary Islands, Büsingen, Heligoland, Livigno …) and
  Northern Ireland (XI, goods count as EU) are not told apart from their country: choose the treatment
  by hand (OPEN_QUESTIONS).
- Rhinvoice does not keep the proofs (customs documents, arrival confirmations) and does not file the
  EC Sales List; it only reminds.
