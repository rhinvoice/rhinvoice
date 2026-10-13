/** The same docs page in the other language: German pages live below /docs/de/. */
export function otherLanguagePath(pathname: string, lang: string): string {
  return lang === "de" ? pathname.replace(/^\/docs\/de\//, "/docs/") : pathname.replace(/^\/docs\//, "/docs/de/");
}

/** The landing page in the language of the docs page. */
export function websiteHref(lang: string): string {
  return lang === "de" ? "https://rhinvoice.com/de/" : "https://rhinvoice.com/";
}
