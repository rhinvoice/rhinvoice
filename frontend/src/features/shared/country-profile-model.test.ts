import { describe, expect, it } from "vitest";

import {
  asksTaxNumber,
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

  it("uses French and Italian terms once the API names them, English until then", () => {
    expect(termsFor(SWISS_PROFILE, "fr-CH").tax_name).toBe("VAT");
    expect(termsFor(SWISS_PROFILE, "it-CH").tax_name).toBe("VAT");
    const french = { ...SWISS_PROFILE.terms.en, tax_name: "TVA" };
    const withFrench = { ...SWISS_PROFILE, terms: { ...SWISS_PROFILE.terms, fr: french } };
    expect(termsFor(withFrench, "fr-CH").tax_name).toBe("TVA");
    expect(termsFor(withFrench, "it-CH").tax_name).toBe("VAT");
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

  it("asks for the tax number where it counts, or once given", () => {
    expect(asksTaxNumber(GERMAN_PROFILE, "")).toBe(true);
    expect(asksTaxNumber(SWISS_PROFILE, "")).toBe(false);
    expect(asksTaxNumber(SWISS_PROFILE, "12/345/67890")).toBe(true);
    expect(asksTaxNumber(undefined, "")).toBe(true);
  });
});
