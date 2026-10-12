import { describe, expect, it } from "vitest";

import {
  DEFAULT_LOCALE,
  intlLocale,
  isLocale,
  LOCALE_NAMES,
  matchLocale,
  SUPPORTED_LOCALES,
} from "@/lib/locale";

describe("locale", () => {
  it("recognises supported locales", () => {
    expect(isLocale("de-CH")).toBe(true);
    expect(isLocale("fr-CH")).toBe(false);
    expect(DEFAULT_LOCALE).toBe("de-CH");
  });

  it("names every locale in its own language", () => {
    expect(Object.keys(LOCALE_NAMES)).toEqual([...SUPPORTED_LOCALES]);
    expect(LOCALE_NAMES["de-AT"]).toBe("Deutsch (Österreich)");
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
    ["fr-CH", "de-CH"],
  ] as const)("maps %j to %s", (tag, expected) => {
    expect(matchLocale(tag)).toBe(expected);
  });
});

describe("intlLocale", () => {
  it("uses en-GB for English and keeps German locales", () => {
    expect(intlLocale("en")).toBe("en-GB");
    expect(intlLocale("de-AT")).toBe("de-AT");
  });
});
