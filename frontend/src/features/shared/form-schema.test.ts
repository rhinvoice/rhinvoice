import { describe, expect, it } from "vitest";

import { fields, toApiDecimal } from "@/features/shared/form-schema";
import { translatorFor } from "@/lib/i18n";

const f = fields(translatorFor("de-CH"), "de-CH");

function message(schema: ReturnType<typeof f.decimal>, value: string): string | undefined {
  const result = schema.safeParse(value);
  return result.success ? undefined : result.error.issues[0]?.message;
}

describe("decimal fields", () => {
  it("may be required", () => {
    const required = f.decimal({ max: 100, decimals: 2, required: true });
    expect(message(required, "")).toBe("Bitte ausfüllen.");
    expect(message(f.decimal({ max: 100, decimals: 2 }), "")).toBeUndefined();
  });

  it("allows negative values only when signed", () => {
    const signed = f.decimal({ max: 100, decimals: 2, signed: true });
    expect(message(signed, "-100")).toBeUndefined();
    expect(message(signed, "-100.01")).toBe("Bitte eine Zahl von -100 bis 100 eingeben.");
    expect(message(f.decimal({ max: 100, decimals: 2 }), "-12")).toBe(
      "Bitte eine Zahl von 0 bis 100 eingeben.",
    );
  });

  it("names the range when a number is too large", () => {
    expect(message(f.decimal({ max: 100, decimals: 2 }), "150")).toBe(
      "Bitte eine Zahl von 0 bis 100 eingeben.",
    );
    // ICU versions group de-CH digits with ’ or ', so compare with one of them.
    expect(
      message(f.decimal({ max: 1_234_567.5, decimals: 2 }), "2000000")?.replace(/\u2019/g, "'"),
    ).toBe("Bitte eine Zahl von 0 bis 1'234'567.5 eingeben.");
  });

  it("gives an example in the locale's format when the input is no number", () => {
    expect(message(f.decimal({ max: 100, decimals: 2 }), "abc")).toBe(
      "Bitte geben Sie eine Zahl ein, z. B. 12.50.",
    );
    const de = fields(translatorFor("de-DE"), "de-DE");
    const result = de.decimal({ max: 100, decimals: 2 }).safeParse("abc");
    expect(result.error?.issues[0]?.message).toBe("Bitte geben Sie eine Zahl ein, z. B. 12,50.");
  });

  it("converts to the API format", () => {
    expect(toApiDecimal("1’234.5", "de-CH")).toBe("1234.5");
    expect(toApiDecimal("abc", "de-CH")).toBe("0");
  });
});
