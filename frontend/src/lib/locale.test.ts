import { describe, expect, it } from "vitest";

import {
  DEFAULT_LOCALE,
  intlLocale,
  isLocale,
  isMachineTranslated,
  LOCALE_NAMES,
  matchLocale,
  numberLocale,
  numericMediumDates,
  SUPPORTED_LOCALES,
  textFor,
  unitName,
} from "@/lib/locale";

describe("locale", () => {
  it("recognises supported locales", () => {
    expect(isLocale("de-CH")).toBe(true);
    expect(isLocale("fr-CH")).toBe(true);
    expect(isLocale("it-CH")).toBe(true);
    expect(isLocale("fr-FR")).toBe(false);
    expect(DEFAULT_LOCALE).toBe("de-CH");
  });

  it("names every locale in its own language", () => {
    expect(Object.keys(LOCALE_NAMES)).toEqual([...SUPPORTED_LOCALES]);
    expect(LOCALE_NAMES["de-AT"]).toBe("Deutsch (Österreich)");
    expect(LOCALE_NAMES["fr-CH"]).toBe("Français");
    expect(LOCALE_NAMES["it-CH"]).toBe("Italiano");
    expect(LOCALE_NAMES.en).toBe("English");
  });

  it.each([
    [undefined, "de-CH"],
    ["", "de-CH"],
    ["de-AT", "de-AT"],
    [" de-DE ", "de-DE"],
    ["de-de", "de-DE"],
    ["de-at", "de-AT"],
    ["de-LI", "de-CH"],
    ["de", "de-CH"],
    ["DE-ch", "de-CH"],
    ["en-US", "en"],
    ["EN", "en"],
    ["fr-CH", "fr-CH"],
    ["fr", "fr-CH"],
    ["fr-FR", "fr-CH"],
    ["FR-be", "fr-CH"],
    ["it-CH", "it-CH"],
    ["it-IT", "it-CH"],
    ["it", "it-CH"],
    ["rm-CH", "de-CH"],
    ["es-ES", "de-CH"],
  ] as const)("maps %j to %s", (tag, expected) => {
    expect(matchLocale(tag)).toBe(expected);
  });
});

describe("intlLocale and numberLocale", () => {
  it("uses en-GB for English and keeps the other locales for words", () => {
    expect(intlLocale("en")).toBe("en-GB");
    expect(intlLocale("de-AT")).toBe("de-AT");
    expect(intlLocale("fr-CH")).toBe("fr-CH");
    expect(intlLocale("it-CH")).toBe("it-CH");
  });

  it("writes Swiss French and Swiss Italian amounts like Swiss German", () => {
    expect(numberLocale("fr-CH")).toBe("de-CH");
    expect(numberLocale("it-CH")).toBe("de-CH");
    expect(numberLocale("de-DE")).toBe("de-DE");
    expect(numberLocale("en")).toBe("en-GB");
  });

  it("writes medium dates numerically in Swiss French and Swiss Italian", () => {
    expect(numericMediumDates("fr-CH")).toBe(true);
    expect(numericMediumDates("it-CH")).toBe(true);
    expect(numericMediumDates("de-CH")).toBe(false);
  });
});

describe("texts from the API", () => {
  it("picks the text in the interface's language", () => {
    const pieces = { de: "Stk.", en: "pcs", fr: "pce", it: "pz." };
    expect(textFor("de-AT", pieces)).toBe("Stk.");
    expect(textFor("en", pieces)).toBe("pcs");
    expect(textFor("fr-CH", pieces)).toBe("pce");
    expect(textFor("it-CH", pieces)).toBe("pz.");
  });

  it("names a unit in the interface's language", () => {
    const hour = { label_de: "Std.", label_en: "h", label_fr: "heure", label_it: "ora" };
    expect(unitName("it-CH", hour)).toBe("ora");
  });

  it("marks French and Italian as machine translated", () => {
    expect(SUPPORTED_LOCALES.filter(isMachineTranslated)).toEqual(["fr-CH", "it-CH"]);
  });
});
