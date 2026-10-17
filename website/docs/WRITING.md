# Writing the Rhinvoice docs

Rules for every page under `src/content/docs/`. English pages live at `<slug>.mdx`, German pages at
`de/<slug>.mdx`, with the same slug, so the language switch and `hreflang` pair them.

## French and Italian

Every page also exists in Swiss French (`fr/<slug>.mdx`) and Swiss Italian (`it/<slug>.mdx`).
`scripts/check.py content` fails when a page is missing in one of the four languages.

- The French and Italian texts were machine-translated. `src/components/Banner.astro` says so above
  each of them and links to the *Translation* issue form; a new French or Italian page gets the
  notice by itself.
- When an English or German page changes, change its French and Italian twin too.
- Link within a language: `/docs/fr/<slug>/`, `/docs/it/<slug>/`.
- French: "vous", TVA, IDE, facture QR, no space before `?`, `!` and `;`. Italian: "Lei", IVA, IDI,
  fattura QR. Amounts as in Switzerland: `CHF 1’234.50`.

## Who reads this

Owners of small businesses, freelancers and their bookkeepers in Switzerland, Liechtenstein, Germany
and Austria. They are not developers. They come from a search engine or from an AI assistant that
quotes the page. Write so that both can take a sentence out of the page and it is still correct.

## Shape of a page

- **Frontmatter**
  - `title`: the task or topic in the words people search for, at most about 60 characters.
    German: "QR-Rechnung in der Schweiz", not "Schweiz-Profil".
  - `description`: 140–160 characters, one or two plain sentences with the main search terms
    (e.g. "Rechnungsprogramm", "QR-Rechnung", "MWST", "kostenlos", "Open Source", the country).
    It is the snippet under the search result.
  - `faq`: 3–5 questions people really ask, each answer self-contained in 1–3 sentences
    (it is shown on the page by `<Faq />` and given to search engines as FAQPage data).
- **First paragraph answers the page's question** in one or two sentences, with the facts
  (answer first, details after). An AI assistant quoting only this paragraph must be right.
- Headings say what the section does or answers ("Welcher MWST-Satz gilt?", "Rechnung ausstellen").
- Concrete facts: rates with their dates, legal references with their official names (Art. 958f OR,
  § 14 UStG, § 11 UStG AT …), file formats, limits, menu paths. Name the source of a rate
  (ESTV, BMF …) and when it applies ("seit 1. Januar 2024").
- Link related pages: `/docs/<slug>/` (English) and `/docs/de/<slug>/` (German), with the
  trailing slash.
- End with `## Häufige Fragen` (German) or `## Questions` (English) followed by `<Faq />`.
- Country and tax pages say once, briefly, that the page is no tax advice.

## New features and release notes

- A page whose feature came after the first public release (0.4.0) gets `since: X.Y.Z` in its
  frontmatter: the title then shows "Ab Version X.Y.Z" / "Since version X.Y.Z", linked to the release
  notes. Only part of a page is new: put `<Since version="X.Y.Z" />` next to it.
- The release notes page (*Neuigkeiten* / *What's new*) is made from `CHANGELOG.md` and its German
  twin `src/data/CHANGELOG.de.md`. Every release adds its entry to both, with the same version
  heading; `scripts/check.py content` compares them.

## Facts: only from the repository

Never invent a feature, a limit or a rate. Take them from:

- `backend/src/rhinvoice/domain/country/*.py` (rates, notices, sources), `backend/src/rhinvoice/domain/`
- `docs/*.md`, `README.md`, `CHANGELOG.md`, `.env.example`, `deploy/compose.yml`, `deploy/demo/README.md`
- the interface's own words in `frontend/src/lib/i18n/messages.de.ts` and `messages.en.ts`: write menu
  paths and button names exactly as the interface shows them, in *italics* (*Rechnungen → Importieren*).

If the repository does not say it, leave it out.

## Language

- German: "Sie", Swiss spelling with "ss" (never "ß"), as on rhinvoice.com. Use each country's own
  terms: MWST and UID in Switzerland and Liechtenstein, USt. and USt-IdNr. in Germany, USt. and UID in
  Austria. Amounts like `CHF 1’234.50` / `1.234,50 EUR` as the interface formats them.
- English: British spelling, plain words.
- Short, direct sentences. No marketing words ("nahtlos", "revolutionär", "seamless"), no dashes as
  asides, no "nicht X, sondern Y" tricks, no emoji.
- Never name other invoicing programs. Say "Ihr bisheriges Programm" / "the program you used before".

## MDX

- Components: `import { Aside, Steps, Tabs, TabItem } from "@astrojs/starlight/components";`
  and `import Faq from "<relative path>/components/Faq.astro";`
  (from `de/<group>/<page>.mdx` that is `../../../../components/Faq.astro`, from `<group>/<page>.mdx`
  `../../../components/Faq.astro`).
- In running text, `{`, `}` and `<` start MDX code: write them inside backticks or as `&lt;`.
- Tables of columns may use `<span class="need yes">Ja</span>` / `<span class="need opt">Wenn vorhanden</span>`.
- Shell commands in ```bash blocks, exactly as in `docs/install.md`.
