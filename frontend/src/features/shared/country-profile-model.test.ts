import { describe, expect, it } from "vitest";

import {
  asksTaxNumber,
  bicMattersForEpc,
  countrySummary,
  offersCashRounding,
  offersCategory,
  offersQrIban,
  profileFor,
  taxCategoryLabel,
  termsFor,
} from "@/features/shared/country-profile-model";
import { translatorFor } from "@/lib/i18n";
import { GERMAN_PROFILE, SWISS_PROFILE } from "@/test/country-profiles";

const de = translatorFor("de-CH");
const en = translatorFor("en");

describe("country profile", () => {
  it("speaks the language of the interface", () => {
    expect(termsFor(SWISS_PROFILE, "de-DE").tax_name).toBe("MWST");
    expect(termsFor(SWISS_PROFILE, "en").tax_name).toBe("VAT");
  });

  it("uses the terms in the interface's language", () => {
    expect(termsFor(SWISS_PROFILE, "fr-CH").tax_name).toBe("TVA");
    expect(termsFor(SWISS_PROFILE, "it-CH").tax_name).toBe("IVA");
    expect(termsFor(SWISS_PROFILE, "de-AT").tax_name).toBe("MWST");
  });

  it("falls back to English when the API names no terms in that language", () => {
    const terms: Partial<typeof SWISS_PROFILE.terms> = { ...SWISS_PROFILE.terms };
    delete terms.fr;
    const withoutFrench = { ...SWISS_PROFILE, terms } as typeof SWISS_PROFILE;
    expect(termsFor(withoutFrench, "fr-CH").tax_name).toBe("VAT");
  });

  it("sums a country up for the first start", () => {
    expect(countrySummary(SWISS_PROFILE, "de-CH", de)).toBe(
      "MWST 8.1% / 2.6% / 3.8% · QR-Rechnung · Rappenrundung",
    );
    expect(countrySummary(GERMAN_PROFILE, "en", en)).toBe("VAT 19% / 7% · EPC QR code");
  });

  it("names the third rate as the country does", () => {
    expect(taxCategoryLabel("special", SWISS_PROFILE, "de-CH", de)).toBe("Sondersatz Beherbergung");
    expect(taxCategoryLabel("special", GERMAN_PROFILE, "de-DE", de)).toBe("Sondersatz");
    expect(taxCategoryLabel("special", undefined, "de-CH", de)).toBe("Sondersatz");
    expect(taxCategoryLabel("reduced", SWISS_PROFILE, "en", en)).toBe("Reduced rate");
  });

  it("offers only the rates the country has", () => {
    expect(offersCategory("special", SWISS_PROFILE)).toBe(true);
    expect(offersCategory("special", GERMAN_PROFILE)).toBe(false);
    expect(offersCategory("reduced", GERMAN_PROFILE)).toBe(true);
    expect(offersCategory("special", null)).toBe(true);
  });
});

describe("fields per country", () => {
  it("finds the profile of a country, also while the list loads", () => {
    expect(profileFor([SWISS_PROFILE, GERMAN_PROFILE], "DE", undefined)).toBe(GERMAN_PROFILE);
    expect(profileFor(undefined, "CH", SWISS_PROFILE)).toBe(SWISS_PROFILE);
    expect(profileFor(undefined, "DE", SWISS_PROFILE)).toBeUndefined();
  });

  it("offers the 5-centime rounding in Switzerland, or while it is on", () => {
    expect(offersCashRounding(SWISS_PROFILE, false)).toBe(true);
    expect(offersCashRounding(GERMAN_PROFILE, false)).toBe(false);
    expect(offersCashRounding(GERMAN_PROFILE, true)).toBe(true);
    expect(offersCashRounding(undefined, false)).toBe(false);
  });

  it("asks for the QR-IBAN where the QR-bill is printed, or while one is saved", () => {
    expect(offersQrIban(SWISS_PROFILE, false)).toBe(true);
    expect(offersQrIban(GERMAN_PROFILE, false)).toBe(false);
    expect(offersQrIban(GERMAN_PROFILE, true)).toBe(true);
    expect(offersQrIban(undefined, false)).toBe(true);
  });

  it("explains the BIC where a Swiss euro account needs it for the EPC QR code", () => {
    expect(bicMattersForEpc(SWISS_PROFILE, "EUR", "ch56 0483 5012 3456 7800 9")).toBe(true);
    expect(bicMattersForEpc(SWISS_PROFILE, "CHF", "CH9300762011623852957")).toBe(false);
    expect(bicMattersForEpc(SWISS_PROFILE, "EUR", "LI2108810000002324013AA")).toBe(false);
    expect(bicMattersForEpc(GERMAN_PROFILE, "EUR", "CH5604835012345678009")).toBe(false);
    expect(bicMattersForEpc(undefined, "EUR", "CH5604835012345678009")).toBe(false);
  });

  it("asks for the tax number where it counts, or once given", () => {
    expect(asksTaxNumber(GERMAN_PROFILE, "")).toBe(true);
    expect(asksTaxNumber(SWISS_PROFILE, "")).toBe(false);
    expect(asksTaxNumber(SWISS_PROFILE, "12/345/67890")).toBe(true);
    expect(asksTaxNumber(undefined, "")).toBe(true);
  });
});
