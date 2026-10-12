export const SUPPORTED_LOCALES = ["de-CH", "de-DE", "de-AT", "en"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "de-CH";

/** Each locale named in its own language, so that everyone finds theirs. */
export const LOCALE_NAMES: Readonly<Record<Locale, string>> = {
  "de-CH": "Deutsch (Schweiz)",
  "de-DE": "Deutsch (Deutschland)",
  "de-AT": "Deutsch (Österreich)",
  en: "English",
};

export function isLocale(value: string): value is Locale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

/** Map a browser language tag (e.g. "de-LI", "en-US") onto a supported locale. */
export function matchLocale(tag: string | undefined): Locale {
  if (tag === undefined || tag === "") {
    return DEFAULT_LOCALE;
  }
  const normalized = tag.trim();
  if (isLocale(normalized)) {
    return normalized;
  }
  const [language, region] = normalized.split("-");
  if (language?.toLowerCase() === "de") {
    const upper = region?.toUpperCase();
    if (upper === "DE") return "de-DE";
    if (upper === "AT") return "de-AT";
    return "de-CH";
  }
  if (language?.toLowerCase() === "en") {
    return "en";
  }
  return DEFAULT_LOCALE;
}

/**
 * The locale passed to Intl. English uses British conventions
 * ("5 January 2026", "1,234.50"), which fit a European audience.
 */
export function intlLocale(locale: Locale): string {
  return locale === "en" ? "en-GB" : locale;
}
