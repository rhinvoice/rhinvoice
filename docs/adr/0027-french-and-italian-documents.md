# 0027 – French and Italian documents

- Status: accepted
- Date: 2026-10-16

## Context
Swiss companies write to customers in Romandy and Ticino in French and Italian. Until 0.7
documents existed in German and English only. Rhinvoice is not meant for companies in France
or Italy, but a French or Italian document may also go to a customer abroad, and German and
Austrian companies have French- or Italian-speaking customers too. The legal notices are the
delicate part: the Swiss VAT Act exists in German, French and Italian (MWSTG, LTVA, LIVA) and
prescribes no wording for these notices, the EU VAT Directive names the mentions in every
official language.

## Decision
- **One language list for all countries.** `Language` has DE, EN, FR and IT. Every country
  profile provides its terms and notices in every language (as it did for English), so any
  company can write a document in any language. No country-dependent filtering of the selects.
- **Swiss variants.** French and Italian are written as in Switzerland (fr-CH, it-CH): "Offre"
  and "Offerta" for the quote, "Note de crédit" and "Nota di credito" for the cancellation
  (as "Credit note" in English), "Rappel" and "Sollecito" for dunning letters, "Meilleures
  salutations" and "Cordiali saluti" in mails.
- **Numbers and dates.** Like German, French and Italian take the number style of the
  company's country: `1’234.50` for Swiss and Liechtenstein companies, `1 234,50` (CLDR fr)
  and `1.234,50` (CLDR it) for German and Austrian ones. For Italian `1’234.50` is CLDR it-CH;
  for French it is a choice: CLDR fr-CH writes `1 234,50`, but Swiss invoices, the QR-bill
  and the other languages of the same company use `1’234.50`, and one company should not print
  two number formats. Dates are CLDR
  long dates ("9 mars 2026", "9 marzo 2026"), as `Intl.DateTimeFormat` writes them; the first
  of the month is an ordinal as usual in both languages ("1er août", "1° agosto").
- **Swiss notices** (CH, LI) use the terms of the law in its French and Italian version:
  "assujetti / assoggettato" (Art. 10), "exonérée / esente" (Art. 23), "lieu de la prestation de
  services / luogo della prestazione di servizi" (Art. 8), and cite "art. 23, al. 2, ch. 1, LTVA"
  and "art. 23 cpv. 2 n. 1 LIVA". Reverse charge for EU customers uses the mention of Art. 226
  point 11a of the VAT Directive in that language ("Autoliquidation", "inversione contabile"),
  because the customer's country asks for it (Art. 219a(1)). Terms follow the ESTV: TVA / IVA,
  IDE / IDI for the UID, "taux spécial pour l'hébergement" / "aliquota speciale per il settore
  alberghiero". The company's VAT number is printed as entered: the ESTV accepts the suffix
  MWST, TVA or IVA in every language.
- **German and Austrian notices** in French and Italian use the mentions of the VAT Directive in
  that language ("Autoliquidation", "franchise pour les petites entreprises", "exonérée";
  "inversione contabile", "franchigia per le piccole imprese", "esente", Directive (EU) 2020/285
  for the small business exemption) and keep the national provision as the law cites it
  (§ 19 UStG, § 6 Abs. 1 Z 27 UStG). Like the English notices they are translations: the
  company can change every notice under *Settings → Texts → Legal notices*.
- **Data.** Languages stay two-letter strings in the database; migration 0019 adds a French and
  an Italian text to the dunning levels (the built-in ones for saved levels) and the ready-made
  text templates in both languages.
- **QR-bill** in the document's language (the `qrbill` library knows de, en, fr, it).
- **The interface** is in French and Italian too (`fr-CH`, `it-CH`, chosen with the globe
  icon or taken from the browser); French and Italian outside Switzerland map to these.
  - *Numbers* in the interface follow de-CH (`CHF 1’234.50`) for both, the style of the
    QR-bill and of Swiss invoices: Intl's fr-CH would write `1 234,50`, its it-CH drops the
    grouping of four-digit amounts (`numberLocale` in `frontend/src/lib/locale.ts`).
  - *Dates* in tables and fields are numeric (`05.01.2026`) like Swiss German, not
    "5 janv. 2026"; long dates keep the month name (`numericMediumDates`).
  - *Typed numbers*: French- and Italian-speaking Swiss write a decimal comma by hand, so in
    fr-CH and it-CH a comma or a dot typed once is the decimal separator ("1,250" is 1.25);
    apostrophes and spaces group thousands. de-CH keeps reading "1,250" as 1250
    (`frontend/src/lib/format/parse-decimal.ts`).
  - *Machine translation*: both catalogues were machine-translated. The language menu marks
    them, and *About Rhinvoice* says so with a button to report a wrong translation; the docs
    and rhinvoice.com pages in French and Italian carry the same notice.
  - *Terms* follow the documents: "Rappel de paiement", "1er rappel", "2e rappel" and
    "Promemoria di pagamento", "1° sollecito", "2° sollecito" for the dunning levels, NAP for
    the Swiss Italian postal code.

## Consequences
- A new language means terms and notices in every country profile, labels, mails, dunning
  texts, units, country names and text templates; the tests require all of them
  (`test_every_language_has_every_term`, the frontend sync test of `DOCUMENT_LANGUAGES`).
- Known limitation: the interface's number style depends on the interface language only. A
  German or Austrian company that uses the French or Italian interface sees Swiss numbers
  (`1’234.50`) on screen, while its PDFs follow its country (`1 234,50`, `1.234,50`).
- An older Rhinvoice cannot read French or Italian documents: the downgrade of 0019 resets
  drafts and defaults to German, issued documents stay as they are.
- Sources are listed in `domain/country/swiss.py`, `de.py` and `at.py`. Not tax advice.
