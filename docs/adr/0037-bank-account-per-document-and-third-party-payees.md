# 0037 – Bank account per document and third-party payees

- Status: accepted
- Date: 2026-10-29

## Context
Every document was paid to the default account of its currency. Users asked (issue #45) to
choose the account per invoice, e.g. a second bank, or the account of a financial service
provider (factoring) that collects the payment in their name. Such an account belongs to
someone else: the QR-bill, the EPC QR code and the e-invoice must name that payee, and the
footer must not offer it on documents paid to the company.

## Decision
- **Choice per document.** Drafts (quotes and invoices) and recurring plans store an optional
  `bank_account_id`. Empty means the default account of the document's currency, as before, so
  existing drafts and API clients keep working. A chosen account must exist and be in the
  document's currency. When it is gone later (deleted, or moved to another currency), drafts and
  plans fall back to the default (the database clears the reference of drafts with `ON DELETE
  SET NULL`; the column is not frozen). Issuing freezes the account in the snapshot as before.
- **Editor.** The select *Bankverbindung* appears in the *Daten* card only when the currency has
  more than one account (plans: next to the currency); the default is preselected, a currency
  change resets the choice.
- **Third-party accounts.** A bank account has `third_party` and, then required, the holder's
  structured address. It is set by the user, never guessed from the holder's name. A third
  party's account may be the default of its currency.
  - The payment block prints "Zahlung an: holder · IBAN" (all document languages), also on
    reminders.
  - Swiss QR-bill: creditor = holder with the third party's address; own accounts keep the
    company's address (SIX IG 3.2.4 names the account holder as creditor).
  - EPC QR code: the beneficiary is the holder already; unchanged.
  - E-invoice (CII, EN 16931 and XRechnung): the chosen account is the payment account; a third
    party is written as Payee (BG-10, `ram:PayeeTradeParty/ram:Name`, BT-59), as BR-17 asks when
    the payee is not the seller. Only the name: the EN 16931 payee has no address.
- **Footer.** *Alle Konten* lists the company's own accounts plus the paying account when that
  one is a third party's; a third party's account never appears on documents not paid to it. A
  third option *Keine* leaves the bank details out (payment block and QR codes stay). The default
  stays *Nur Rechnungswährung*; existing documents look as before.
- **No link between bank accounts and payment texts.** Proposed in the issue and rejected: it
  would couple two settings for one case. Users who mostly invoice through a provider mark the
  provider's account and its payment text as default instead.
- Snapshots written before have no `third_party` and read as own accounts.

## Consequences
- One more select in the editor, but only for users with several accounts in a currency.
- Deleting a bank account never blocks: drafts and plans fall back, issued documents are frozen.
- The e-invoice samples validated in CI (KoSIT, Mustang) include a third-party payee in EUR
  (Germany) and in CHF (Switzerland).
