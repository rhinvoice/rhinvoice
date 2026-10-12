import { intlLocale, type Locale } from "@/lib/locale";

const cache = new Map<Locale, Intl.DisplayNames>();

/** Localised country name for an ISO 3166-1 alpha-2 code ("CH" → "Schweiz"). */
export function countryName(code: string, locale: Locale): string {
  let names = cache.get(locale);
  if (names === undefined) {
    names = new Intl.DisplayNames([intlLocale(locale)], { type: "region", fallback: "none" });
    cache.set(locale, names);
  }
  return names.of(code) ?? code;
}

export interface CountryOption {
  readonly code: string;
  readonly name: string;
}

/**
 * Countries sorted by their localised name, with the most relevant ones
 * (CH, LI, DE, AT) first so that they are reachable without scrolling.
 */
export function countryOptions(codes: readonly string[], locale: Locale): CountryOption[] {
  const preferred = ["CH", "LI", "DE", "AT"];
  const collator = new Intl.Collator(intlLocale(locale));
  const options = codes.map((code) => ({ code, name: countryName(code, locale) }));
  const top = preferred.flatMap((code) => options.filter((option) => option.code === code));
  const rest = options
    .filter((option) => !preferred.includes(option.code))
    .sort((a, b) => collator.compare(a.name, b.name));
  return [...top, ...rest];
}
