export const SUPPORTED_LOCALES = ["de-CH", "de-DE", "de-AT", "fr-CH", "it-CH", "en"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "de-CH";

/** Each locale named in its own language, so that everyone finds theirs. */
export const LOCALE_NAMES: Readonly<Record<Locale, string>> = {
  "de-CH": "Deutsch (Schweiz)",
  "de-DE": "Deutsch (Deutschland)",
  "de-AT": "Deutsch (Österreich)",
  "fr-CH": "Français",
  "it-CH": "Italiano",
  en: "English",
};

export function isLocale(value: string): value is Locale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

/** Map a browser language tag (e.g. "de-LI", "fr-FR", "en-US") onto a supported locale. */
export function matchLocale(tag: string | undefined): Locale {
  if (tag === undefined || tag === "") {
    return DEFAULT_LOCALE;
  }
  const normalized = tag.trim();
  if (isLocale(normalized)) {
    return normalized;
  }
  const [, region] = normalized.split("-");
  const language = normalized.split("-", 1).join("").toLowerCase();
  switch (language) {
    case "de": {
      const upper = region?.toUpperCase();
      if (upper === "DE") return "de-DE";
      if (upper === "AT") return "de-AT";
      return "de-CH";
    }
    // French and Italian are offered in their Swiss variants only.
    case "fr":
      return "fr-CH";
    case "it":
      return "it-CH";
    case "en":
      return "en";
    default:
      return DEFAULT_LOCALE;
  }
}

/**
 * The locale passed to Intl for words: month names, relative times, country names.
 * English uses British conventions ("5 January 2026"), which fit a European audience.
 */
export function intlLocale(locale: Locale): string {
  return locale === "en" ? "en-GB" : locale;
}

/**
 * The locale passed to Intl for numbers and amounts. Swiss French and Swiss Italian
 * write amounts like Swiss German ("CHF 1’234.50"), as on the QR-bill; Intl's fr-CH
 * would give "1 234,50" and its it-CH drops the grouping of four-digit amounts.
 */
export function numberLocale(locale: Locale): string {
  return locale === "fr-CH" || locale === "it-CH" ? "de-CH" : intlLocale(locale);
}

/** Swiss French and Swiss Italian show dates as 05.01.2026 like Swiss German, not "5 janv. 2026". */
export function numericMediumDates(locale: Locale): boolean {
  return locale === "fr-CH" || locale === "it-CH";
}

/**
 * Pick between a German and an English text the API sends (e.g. unit names):
 * German for the German locales, English for all others.
 */
export function germanOrEnglish(locale: Locale, german: string, english: string): string {
  return locale.startsWith("de") ? german : english;
}

/** French and Italian texts are machine translated; their users are asked for corrections. */
export function isMachineTranslated(locale: Locale): boolean {
  return locale === "fr-CH" || locale === "it-CH";
}
