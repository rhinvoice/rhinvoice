# 0017 – Country profiles

- Status: accepted
- Date: 2026-10-12
- Supersedes in part: 0008 (where mandatory fields and the payment code choice live)

## Context
What differs between Switzerland, Liechtenstein, Germany and Austria was spread over about forty places:
rate tables, notice tables, the mandatory field check, PDF labels, the number format, the mail greeting,
the payment codes, the import and several frontend modules each held their own `if country in {CH, LI}`.
Someone adding a country would have had to find all of them, and the copies drifted apart (Austria's
13 % rate was read as the 10 % one by the import, German documents called the customer's VAT ID
"UID", the wizard repeated the rates as text). The plan foresaw a `CountryProfile` per country; it
had not been built.

## Decision
- **One profile per company country** in `domain/country/<code>.py`, a frozen `CountryProfile`:
  - the VAT law (`VatRules`: the EU VAT Directive or the Swiss MWSTG) and the VAT area (CH with LI),
  - dated rate sets,
  - the terms per document language: tax name, VAT number labels, the small business label, the name of
    the third rate, the mail greeting and the legal notice per tax treatment,
  - `check_invoice`, the mandatory details of an invoice,
  - number style, payment codes (Swiss QR-bill, EPC on every euro invoice, EPC to the EEA),
    default currency, whether the 5-centime rounding is offered and whether the national tax number
    can stand in for the VAT ID,
  - the official sources of all of it.
- **The rest of Rhinvoice asks the profile** (`profile_of(country)`) and names no country. The tax
  treatment depends on `VatRules` instead of country codes: EU countries share the Directive's logic,
  so a new EU country needs no change there.
- **Shared rules live in shared modules**, not in one country's profile: `domain/country/swiss.py` holds
  what Switzerland and Liechtenstein share. import-linter keeps the profiles independent of each other,
  and only `domain/country/registry.py` imports them.
- **The API carries the profile.** `GET /api/reference/country-profiles` lists them (first start), and
  every company response carries its own (`profile`). The frontend shows tax names, rates, labels and
  fields from it and no longer knows countries itself.
- **Contract tests define a complete country** (`tests/unit/domain/test_country_profiles.py`): every
  `Country` has a profile, rates leave no gap, every language has every term and every notice the VAT
  law needs, payment codes fit the currency, sources are links. Sync tests keep the frontend's list
  of company countries and of EU member states equal to the backend's; the demo data needs an entry
  for every country.
- **Issued documents keep their tax content.** Rates and notices are frozen when a document is
  issued (ADR 0005, 0006). Labels and the number format are read from the profile when a document is
  rendered, as before; the PDF of an issued document is kept from its first rendering on (ADR 0007).

## Consequences
- A new country is one module plus a line in the registry, the enum, the import-linter contracts, the
  frontend's list of company countries and the demo data, guided by `docs/adding-a-country.md` and
  failing tests. EU countries reuse the treatment logic; a country with its own VAT law outside the
  EU needs a `VatSystem` of its own.
- Languages are still German and English. A country whose documents need another language needs a
  new `Language` first (message catalogues, PDF labels, mail texts), which is a larger step.
- National e-invoice networks (e.g. Italy's SDI) are not part of a profile; they would be their own
  module next to ZUGFeRD and XRechnung (ADR 0013).
- Fixed on the way: the import reads rates from the company's country (13 % in Austria is its own rate),
  German documents print "Ihre USt-IdNr.", the wizard shows the rates of the day, the 5-centime
  rounding and the QR-IBAN field are only offered where they apply, and the tax name is "USt."
  everywhere.
