# Adding a country

Rhinvoice keeps everything that differs between company countries in one **country profile** per
country (see [ADR 0017](adr/0017-country-profiles.md)). This guide adds a country, using the
Netherlands (`NL`) as the example. Tests tell you what is missing, so you know when you are done.

Before you start, open an issue with the **Tax or legal rule** form. Name the country and link the
official sources: the VAT law, the rates, and what an invoice must state. Rhinvoice gives no tax
advice, but every rule in it names its source.

## What a profile covers, and what it does not

A profile holds:
- the VAT law, with a choice between the EU VAT Directive and the Swiss MWSTG
- the VAT area
- the rates, with the date each applies from
- the legal notices, labels and mail greeting, in German and English
- what an invoice must state
- the number style, payment codes and default currency
- whether rounding to 0.05 is offered and whether the national tax number counts as a tax ID
- the official sources of all of the above

Some things are not in a profile yet. Check them first, because they decide how big the job is:
- **Currencies:** Rhinvoice knows CHF and EUR. A country that invoices in its own currency (PLN, SEK,
  …) also needs that currency added (`domain/shared/money.py`) and its rounding checked.
- **Languages:** documents are written in German or English. A country whose customers expect
  invoices in their own language needs a new `Language` first: message catalogues, PDF labels,
  notices and mail texts.
- **National e-invoice networks:** for example Italy's SDI, or France's platforms from 2026. Every
  invoice already embeds ZUGFeRD / Factur-X (EN 16931). A mandatory national network would be a
  module of its own next to `infrastructure/einvoice`.
- **VAT law outside the EU:** EU countries share the treatment logic in `domain/tax/treatment.py`.
  A country with its own VAT law needs its own `VatSystem` and its own rules there.

## Steps

### 1. The country code

Add the code to `Country` in `backend/src/rhinvoice/domain/shared/country.py`:

```python
class Country(StrEnum):
    CH = "CH"
    LI = "LI"
    DE = "DE"
    AT = "AT"
    NL = "NL"
```

### 2. The profile

Create `backend/src/rhinvoice/domain/country/nl.py`. Copy `de.py` or `at.py`; both are EU countries.
Then change the following:

- **The module docstring:** list every source with the article of the law and the date you checked it.
- **`rates`:** the dated `TaxRateSet`s, oldest first, without gaps. The last one has
  `valid_to=None`. `special` is the third rate, or `None` if there is none.
- **`terms`:** the words for German and English documents. `notices` needs a text for every
  treatment the VAT law knows: reverse charge, export, small business, exempt, intra-Community
  supply and export delivery. The texts must say what the law asks the invoice to say.
- **`check_invoice`:** raise a `ValidationError` with a `code` when an invoice lacks a detail the
  law requires, such as the VAT ID above an amount. Reuse the existing codes
  (`company_vat_number_missing`, `company_tax_id_missing`, `customer_vat_number_required`), so the
  interface already explains them.
- **`number_style`, `payment_codes`, `default_currency`, `cash_rounding`, `tax_number`:** see the
  docstrings in `domain/country/profile.py`. A euro country in SEPA prints the EPC QR code
  (`PaymentCode.EPC`).
- **`sources`:** the links to the official pages.

### 3. Register it

- Add `nl.PROFILE` to `domain/country/registry.py`.
- Add `rhinvoice.domain.country.nl` to both country contracts of import-linter in
  `backend/pyproject.toml`: the profiles stay independent, and only the registry imports them.

### 4. Demo data

Add addresses in the country to `HOME_PLACES` in `backend/src/rhinvoice/application/demo/handlers.py`.
Add an example bank account to `DEMO_ACCOUNTS` and `ACCOUNT_SETS`. Use the IBAN examples of the
national bank association or the EPC, never a real account.

### 5. The frontend

Add the code to `COMPANY_COUNTRIES` in `frontend/src/features/company/company-form-model.ts`.
Everything else (tax name, rates, labels, which fields to show) comes from the profile through the
API. Then regenerate the API client:

```bash
make api
```

### 6. Check

```bash
make qa
```

These tests guide you:
- `tests/unit/domain/test_country_profiles.py` checks that the profile is complete: rates, terms,
  notices, payment codes and sources.
- `tests/unit/test_frontend_sync.py` checks that the frontend's list of countries is the backend's.
- `tests/unit/application/test_demo.py` checks the demo data.

Then write tests for what is particular to the country:
- `check_invoice`, in `tests/unit/domain/test_country_requirements.py`
- treatments across borders, in `tests/unit/domain/test_tax_rates.py`
- a printed invoice, in `tests/unit/test_rendering.py`

Finally, issue an invoice in a test installation (`make demo`) and look at the PDF.

### 7. Pull request

Describe the sources in the pull request, attach a PDF of an invoice, and tick the CLA box (see
[CONTRIBUTING.md](../CONTRIBUTING.md)).
