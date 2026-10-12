import type { components } from "@/api/client";
import { formatPercent } from "@/lib/format";
import type { T } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";

/** What differs between the company countries; comes from the API, not from code here. */
export type CountryProfile = components["schemas"]["CountryProfileResponse"];
export type CountryTerms = components["schemas"]["CountryTermsResponse"];
type TaxCategory = "standard" | "reduced" | "special" | "zero" | "exempt";

/** The country's words in the interface language (German for every German locale). */
export function termsFor(profile: CountryProfile, locale: Locale): CountryTerms {
  return locale === "en" ? profile.terms.en : profile.terms.de;
}

/** "MWST 8.1 % / 2.6 % / 3.8 % · QR-Rechnung": the country at a glance (first start). */
export function countrySummary(profile: CountryProfile, locale: Locale, t: T): string {
  const { standard, reduced, special } = profile.rates;
  const rates = [standard, reduced, ...(special === null ? [] : [special])]
    .map((rate) => formatPercent(rate, locale))
    .join(" / ");
  const codes = profile.payment_codes
    .filter((code) => code !== "epc_to_eea")
    .map((code) => t(`paymentCode.${code}`));
  const rounding = profile.cash_rounding ? [t("company.cashRounding")] : [];
  return [`${termsFor(profile, locale).tax_name} ${rates}`, ...codes, ...rounding].join(" · ");
}

/** The name of a tax category; the third rate is named by the country (e.g. accommodation). */
export function taxCategoryLabel(
  category: TaxCategory,
  profile: CountryProfile | null | undefined,
  locale: Locale,
  t: T,
): string {
  const special =
    profile === null || profile === undefined ? null : termsFor(profile, locale).special_rate;
  return category === "special" && special !== null ? special : t(`tax.${category}`);
}

/** Whether the country has a category (e.g. no third rate in Germany); unknown: all. */
export function offersCategory(
  category: TaxCategory,
  profile: CountryProfile | null | undefined,
): boolean {
  return (
    profile === null ||
    profile === undefined ||
    category !== "special" ||
    profile.rates.special !== null
  );
}

/** The profile of a country: from the list, else the saved company's while the list loads. */
export function profileFor(
  profiles: readonly CountryProfile[] | undefined,
  country: string,
  saved: CountryProfile | undefined,
): CountryProfile | undefined {
  return (
    profiles?.find((profile) => profile.country === country) ??
    (saved?.country === country ? saved : undefined)
  );
}

/** The 5-centime rounding is offered where the country knows it, and stays while it is on. */
export function offersCashRounding(profile: CountryProfile | undefined, on: boolean): boolean {
  return on || (profile?.cash_rounding ?? false);
}

/** The QR-IBAN is asked for where the Swiss QR-bill is printed, and shown while one is saved. */
export function offersQrIban(profile: CountryProfile | undefined, saved: boolean): boolean {
  return saved || (profile?.payment_codes.includes("swiss_qr_bill") ?? true);
}

/** The national tax number is asked for where it can stand in for the VAT ID, or once given. */
export function asksTaxNumber(profile: CountryProfile | undefined, value: string): boolean {
  return value !== "" || (profile?.tax_number ?? true);
}
