# 0013 – E-invoices (ZUGFeRD / Factur-X, XRechnung)

- Status: accepted
- Date: 2026-10-11

## Context
In Germany, businesses must be able to receive e-invoices since 2025 (§ 14 UStG) and must issue them
domestically between businesses in stages: from 2027 with more than 800'000 EUR turnover in the previous year,
from 2028 all of them (transitional rules § 27 Abs. 38 UStG); small businesses are exempt (§ 34a UStDV).
Public authorities require XRechnung. In Austria and Switzerland,
accounting programs increasingly read ZUGFeRD PDFs directly. For people, the PDF remains the
familiar document.

## Decision
- **ZUGFeRD / Factur-X, profile EN 16931**, in the PDF of every issued invoice and cancellation invoice,
  for all countries; can be switched off in the print template (default: on). One file for people and programs.
- **XRechnung 3.0 (CII)** as a separate XML file for download, for German public authorities. The
  invoice's *reference* field is the buyer reference (BT-10), for public authorities the Leitweg-ID.
  Since 0.8.0 a German customer's fixed buyer reference wins over it ([ADR 0028](0028-buyer-reference-per-customer.md)).
- **A mirror of what is printed:** every amount in the e-invoice is an amount in the PDF; the domain
  recalculates nothing. Cancellation invoices are credit notes (381) with positive amounts and a reference to
  the cancelled invoice. Gross prices become net amounts: the net of each tax group is the
  printed one, and its lines share it proportionally (remainder to the largest). Every line adds up to the
  cent: quantity × net price − discount + charge = line amount; the rounding of the net price derived from the
  gross price (4 decimal places) appears in it as a "Rounding" discount or charge,
  and discounts on credit note lines are negative like the line (property test with hypothesis).
- **Tax categories** according to UNCL 5305: S, Z, E, AE (reverse charge, also CH → EU), G (export).
  Intra-community supplies of goods are "K" since goods and services are told apart (ADR 0014).
  Small businesses without a VAT number (MWST-Nummer) and tax number (CH/LI) are "O" (not subject to VAT), German
  and Austrian small businesses are "E" with their notice as the exemption reason.
- **Seller identifiers:** the Swiss UID is the company identifier (BT-30, scheme 0183) and, for
  companies subject to VAT, at the same time the VAT number (BT-31), even if entered without the suffix "MWST". German
  tax numbers go into BT-32, the commercial register entry into BT-30 or BT-33, respectively.
- **Only complete e-invoices:** if something the rules require is missing (e.g. BR-CO-26, BR-AE-02,
  BR-DE-*), no e-invoice is embedded or no XRechnung is generated, respectively; the invoice states what
  was missing. The PDF is created anyway. Even before issuing, the dialog warns as long as
  the details can still be completed.
- **Cancellation invoices as XRechnung** name the account of the cancelled invoice as payment instructions
  (BR-DE-1 also applies to credit notes); embedded in the PDF they carry none. QR-IBANs are never stated as
  SEPA credit transfer (58).
- **XML written in-house** (standard library, fully typed) instead of with drafthorse: the mapping
  is the tricky part, not the serialisation; the official validators take care of the checking.
  The rules (identifiers, category "O", missing details) live in the application layer and
  are checked with mutation tests; the mapping to CII lives in the infrastructure.
- **PDF/A-3b in Python** (pypdf) on top of Chromium's PDF: identification, sRGB output intent (profile from
  LittleCMS, freely usable) and XMP with the Factur-X extension; pages and tags remain unchanged.
  Gotenberg's own PDF/A conversion runs via LibreOffice and replaces the fonts. All PDFs
  (including quotes and reminders) are PDF/A-3b.
- **Archived:** the embedded XML is stored together with the PDF (insert only, never modify), so every
  invoice reliably knows whether its PDF is an e-invoice.
- **Checked in CI** (`make einvoice-qa`): sample invoices for every tax case against the
  KoSIT validator (EN 16931 and XRechnung) and, as PDF, against Mustang (ZUGFeRD, PDF/A-3 with veraPDF).
  Warnings count as errors.

## Consequences
- Invoices from German companies to domestic businesses fulfil the obligation to issue e-invoices if the
  e-invoice is actually embedded (the invoice shows this); XRechnung additionally needs
  the company's e-mail and phone number, the customer's e-mail and the reference.
- Issued invoices never change: whatever was missing at issuing only applies to the next ones.
- UBL, Peppol delivery and ebInterface (AT, public sector) are not implemented.
