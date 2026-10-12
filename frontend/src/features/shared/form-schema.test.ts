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
    expect(message(signed, "-100.01")).toBe("Bitte geben Sie eine Zahl ein, z. B. 150.00.");
    expect(message(f.decimal({ max: 100, decimals: 2 }), "-1")).toBe(
      "Bitte geben Sie eine Zahl ein, z. B. 150.00.",
    );
  });

  it("converts to the API format", () => {
    expect(toApiDecimal("1’234.5", "de-CH")).toBe("1234.5");
    expect(toApiDecimal("abc", "de-CH")).toBe("0");
  });
});
