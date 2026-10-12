import { describe, expect, it } from "vitest";

import { countryName, countryOptions } from "@/lib/countries";

describe("countries", () => {
  it("names countries in the UI language", () => {
    expect(countryName("CH", "de-CH")).toBe("Schweiz");
    expect(countryName("LI", "de-DE")).toBe("Liechtenstein");
    expect(countryName("AT", "en")).toBe("Austria");
    expect(countryName("CH", "de-CH")).toBe("Schweiz");
  });

  it("falls back to the code for unknown regions", () => {
    expect(countryName("XK", "de-CH")).toBe("Kosovo");
    expect(countryName("AA", "de-CH")).toBe("AA");
  });

  it("puts the DACH countries first and sorts the rest by name", () => {
    const options = countryOptions(["FR", "AT", "CH", "DE", "BE", "LI", "AL"], "de-CH");
    expect(options.map((option) => option.code)).toEqual([
      "CH",
      "LI",
      "DE",
      "AT",
      "AL",
      "BE",
      "FR",
    ]);
    expect(options[4]).toEqual({ code: "AL", name: "Albanien" });
  });

  it("works without any preferred country", () => {
    expect(countryOptions(["FR", "BE"], "en").map((option) => option.name)).toEqual([
      "Belgium",
      "France",
    ]);
  });
});
