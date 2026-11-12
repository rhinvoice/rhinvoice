# 0044 – Own tax rates

- Status: proposed
- Date: 2026-11-12

## Context
A line takes one of fixed categories (standard, reduced, special, zero, exempt, pass-through),
and the country profile gives the rate per date (ADR 0017). That covers the normal rates of CH,
LI, DE and AT, but not the special schemes: German farmers and foresters charge average rates
under § 24 UStG (#80), Austria has § 22 UStG 1994, and the third rate means accommodation in CH
and LI but the second reduced rate in AT. Each such case would need code, a release and a new
category, and a notice text that only fits that case.

The e-invoice must stay right whatever a user sets up: EN 16931 ties the category code to the
rate (S needs a rate above zero, Z and E need zero, E needs an exemption reason).

## Decision
- **A tax rate belongs to the company**: name, e-invoice category (S, Z or E), an exemption
  reason for E, an optional notice printed on documents that use it, and dated values
  (percentage, valid from). A change of the percentage adds a value with its date; values that
  documents were issued with never change.
- **Country presets** bring the rates of each country with their official source (the data of
  today's profiles, ADR 0017) and special schemes such as § 24 UStG. Setting up a company takes
  the presets of its country; further ones are taken over with one click. Users can rename,
  hide or add rates and change texts.
- **Rates that come from a preset keep its key.** When the law changes (as CH did on
  2024-01-01), a release adds the new dated value to those rates, unless the user changed the
  percentages; the settings show what was added. Own rates are the user's to keep.
- **Checked on save**, with a message that says why: S needs a percentage above zero, Z and E
  need zero, E needs a reason. The category is preselected (presets bring it; a new rate above
  zero suggests S, at zero the form asks whether it is zero-rated or exempt). The settings link
  a docs page that explains the choice (4 languages).
- **What stays logic in code**: reverse charge, export, intra-Community supplies, small
  businesses (they decide per document whether any VAT is charged, as now) and pass-through
  items (ADR 0039, not a rate). A rate only answers what a domestic taxable line costs.
- **Lines and articles refer to a rate.** A draft takes the value valid on the date of supply,
  as today. Issuing freezes on each line the percentage, the category, the name and the notice,
  so issued documents never depend on the settings again. Totals group by category and
  percentage (unchanged).
- **Migration**: every company gets the presets of its country; existing lines, articles,
  recurring plans and import mappings point to the rate of their old category. Issued documents
  keep their frozen percentages and look the same.
- **CSV import** maps a percentage to the rate with that value on the document date, else
  reports it as today.
- Presets pass KoSIT and Mustang in the e-invoice tests; each preset names its source.

## Open questions (decided with the UI variants)
- Austria § 22 UStG 1994: the notice there replaces the VAT ID; a switch per rate or part of
  the preset?
- Whether hidden rates stay selectable on articles that already use them.

## Consequences
- Special schemes are data, not code: a new one is a preset or a user's own rate.
- The category enum disappears from lines, articles, the API and the import; the generated API
  types change, and the API makes no compatibility promise before 1.0.
- A new settings page *Tax rates* and a changed rate choice in the line editor and the article
  form; variants are shown before building (ADR process, issue #80).
- Large change with a migration of every document line; it gets its own release candidate.
