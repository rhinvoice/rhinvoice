# 0008 – Payment parts (QR-bill, EPC-QR) and mandatory fields per country

- Status: accepted
- Date: 2026-10-11
- Superseded in part by: 0017 (mandatory fields and the choice of payment codes now live in the country profiles)

## Context
CLAUDE.md §4 and §9 require the Swiss QR-bill for CH/FL and the EPC-QR code ("GiroCode") for DE/AT.
Before issuing, the country's mandatory fields must be checked.

## Decision
- **References in the domain** (`domain/payment/reference.py`): QR reference (27 digits, modulo 10 recursive,
  SIX Implementation Guidelines QR-bill, appendix B) from the year of issue and the digits of the document number;
  creditor reference according to ISO 11649 (`RF` + check digits MOD 97-10) from the document number. Both depend only on
  the immutable number and therefore need not be stored. Secured with the official examples
  and property tests.
- **QR-bill** (`infrastructure/payment/qr_bill.py`, library `qrbill`): for invoices of companies in CH/FL
  with an account with a CH/LI IBAN in CHF or EUR and a positive amount. With a QR-IBAN → QRR reference, otherwise SCOR.
  Structured addresses (the domain's field lengths match those of the QR-bill; personal names are truncated to
  70 characters; the address addition has no field in the structured format). Texts are restricted to the character set
  from chapter 4.1.1 (Basic Latin, Latin-1, Latin Extended-A, Ș ș Ț ț €); other characters become their
  base letter or are dropped. If the library rejects the payer's data, "Payable by" stays empty
  (the payer fills it in). If a number is too long for a reference (> 22 digits or > 21 characters, respectively), payment
  is made to the IBAN without a reference.
  The payment part sits at the bottom of a **separate page** (in the library's size, never scaled, separator line
  with scissors), without a footer. This is permitted and independent of how long the invoice is. The preview
  shows it as a second sheet.
- **Drafts** get no payable code (neither QR-bill nor EPC), but a placeholder in the
  same place: the reference only comes into being with the number, and a payment on a draft could
  not be matched.
- **EPC-QR** (`infrastructure/payment/epc.py`, `segno.helpers.make_epc_qr`): for invoices in EUR of companies
  in DE/AT with a EUR account, remittance information "Rechnung <number>"; next to the payment terms.
  Addendum 2026-10: also for EUR invoices of companies in CH/FL to customers in the EEA (EU, Iceland, Norway;
  customers in FL pay with the QR-bill), in addition to the QR-bill. Banking apps there read the EPC code,
  but mostly not the Swiss QR-bill; CH and FL participate in SEPA. A Swiss account lies outside
  the EEA: without a BIC the SEPA rulebook still requires one, so in that case there is no EPC code. The
  account holder is put into the code as the beneficiary, because banks in the EU match the name against the account
  (verification of payee); the QR-bill likewise names the account holder as the payee.
- The payment codes live in `infrastructure/payment/` instead of `infrastructure/country/*`: the EPC code applies
  equally to DE and AT, and the country packages must not know each other (import-linter).
- **References are not stored**, but derived from the number and the year of issue. Therefore the
  algorithm must never change (tests pin the exact values). Within one number pattern the
  QR references are unique; if the pattern changes in the middle of a year, two numbers could have the same digits
  (see OPEN_QUESTIONS 14).
- **Mandatory fields** (`domain/country/requirements.py`), checked when issuing invoices. Cancellations are
  not checked: they repeat the parties of the invoice, and cancelling is the only way to correct one.
  - CH/FL: the company's VAT number (MWST-Nummer), unless "not subject to VAT" (Art. 26 Abs. 2 lit. a MWSTG).
  - DE: tax number or USt-IdNr. (§ 14 Abs. 4 Nr. 2 UStG), except small-amount invoices up to 250 EUR
    (§ 33 UStDV). Also applies to small businesses (§ 34a UStDV; a small-business ID belongs in the
    tax number field).
  - AT: the company's UID (§ 11 Abs. 1 Z 3 lit. i UStG), not for invoices up to 400 EUR (§ 11 Abs. 6) and not
    for small businesses; above 10'000 EUR gross also the UID of the business customer (§ 11 Abs. 1 Z 3 lit. b),
    simplified as customers in Austria.
  - Amounts in currencies other than EUR are never treated as small amounts (conservative).
- **Date of supply**: without a service period, the invoice prints the invoice date as the date of supply (mandatory
  under § 14 Abs. 4 Nr. 6 UStG and § 11 Abs. 1 Z 3 lit. d UStG AT; in CH/FL only required if it differs, Art. 26
  Abs. 2 lit. d MWSTG, but does no harm). A cancellation repeats the date of supply of its invoice.
- `qrbill` and `segno` are forbidden for domain and application via import-linter.

## Consequences
- Existing installations without a VAT number can issue again only once they enter the number or
  choose "not subject to VAT". The error message says where.
- PDF/A-3 and e-invoicing follow in phase 7.
