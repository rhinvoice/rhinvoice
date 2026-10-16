/**
 * The languages of the docs and where their pages live: English at /docs/, the others below
 * /docs/<code>/ with the same paths.
 */
export const LANGUAGES = ["de", "en", "fr", "it"] as const;
export type Language = (typeof LANGUAGES)[number];

/** The language of a Starlight route ("en" for anything unknown). */
export function languageOf(lang: string): Language {
  return (LANGUAGES as readonly string[]).includes(lang) ? (lang as Language) : "en";
}

/** The docs path prefix of a language: "/docs/" for English, "/docs/de/" for German. */
export function docsBase(lang: string): string {
  const language = languageOf(lang);
  return language === "en" ? "/docs/" : `/docs/${language}/`;
}

/** The same docs page in another language. */
export function languagePath(pathname: string, from: string, to: string): string {
  const rest = pathname.startsWith(docsBase(from)) ? pathname.slice(docsBase(from).length) : "";
  return `${docsBase(to)}${rest}`;
}

/** The landing page in the language of the docs page. */
export function websiteHref(lang: string): string {
  const language = languageOf(lang);
  return language === "en" ? "https://rhinvoice.com/" : `https://rhinvoice.com/${language}/`;
}
