import { describe, expect, it } from "vitest";

import {
  defaultRateId,
  PASS_THROUGH,
  percentOn,
  percentsOn,
  resolvedChoice,
  shortRate,
  taxChoiceOf,
  taxChoiceToRequest,
  taxOptions,
} from "@/features/shared/tax-rate-model";
import { translatorFor } from "@/lib/i18n";
import { SWISS_RATES, taxRate } from "@/test/tax-rates";

const t = translatorFor("de-CH");
const [standard] = SWISS_RATES;

describe("tax rate model", () => {
  it("takes the percentage in force on a day", () => {
    expect(percentOn({ values: standard?.values ?? [] }, "2023-12-31")).toBe("7.7");
    expect(percentOn({ values: standard?.values ?? [] }, "2024-01-01")).toBe("8.1");
    expect(percentOn({ values: standard?.values ?? [] }, "2017-12-31")).toBeNull();
  });

  it("leaves rates out that are not valid yet", () => {
    expect(percentsOn(SWISS_RATES, "2026-11-12")).toEqual({
      "rate-standard": "8.1",
      "rate-reduced": "2.6",
      "rate-zero": "0",
      "rate-exempt": "0",
      "rate-old": "8.1",
    });
  });

  it("picks the default rate as the server does", () => {
    expect(defaultRateId(SWISS_RATES)).toBe("rate-standard");
    const own = [taxRate({ id: "own", name: "Eigener" }), ...SWISS_RATES.slice(1)];
    expect(defaultRateId(own)).toBe("own");
    const hidden = SWISS_RATES.map((rate) =>
      rate.category === "S" ? { ...rate, hidden: true } : rate,
    );
    expect(defaultRateId(hidden)).toBeNull();
    expect(resolvedChoice(SWISS_RATES, "")).toBe("rate-standard");
    expect(resolvedChoice(SWISS_RATES, "rate-zero")).toBe("rate-zero");
  });

  it("converts between the stored line and the choice", () => {
    expect(taxChoiceOf({ tax_category: "pass_through", tax_rate_id: null })).toBe(PASS_THROUGH);
    expect(taxChoiceOf({ tax_category: "standard", tax_rate_id: "rate-standard" })).toBe(
      "rate-standard",
    );
    expect(taxChoiceOf({ tax_category: "standard", tax_rate_id: null })).toBe("");
    expect(taxChoiceToRequest(PASS_THROUGH)).toEqual({ tax_rate_id: null, pass_through: true });
    expect(taxChoiceToRequest("")).toEqual({ tax_rate_id: null, pass_through: false });
    expect(taxChoiceToRequest("rate-zero")).toEqual({
      tax_rate_id: "rate-zero",
      pass_through: false,
    });
  });

  it("groups the rates into taxable and without tax", () => {
    const percents = percentsOn(SWISS_RATES, "2026-11-12");
    const options = taxOptions(SWISS_RATES, "", percents, "Durchlaufender Posten", "de-CH", t);
    expect(options.taxed.map((option) => option.label)).toEqual([
      "Normalsatz – 8.1%",
      "Reduzierter Satz – 2.6%",
      "Weinbau",
    ]);
    expect(options.untaxed).toEqual([
      { value: "rate-zero", label: "0 % (steuerbar) – 0%" },
      { value: "rate-exempt", label: "Von der Steuer ausgenommen – 0%" },
      { value: PASS_THROUGH, label: "Durchlaufender Posten" },
    ]);
  });

  it("offers a hidden rate only where it is chosen", () => {
    const percents = percentsOn(SWISS_RATES, "2026-11-12");
    const options = taxOptions(SWISS_RATES, "rate-old", percents, "", "de-CH", t);
    expect(options.taxed.map((option) => option.label)).toContain(
      "Alter Satz (ausgeblendet) – 8.1%",
    );
  });

  it("shows the percentage in short, with the name where it is not unique", () => {
    const percents = percentsOn(SWISS_RATES, "2026-11-12");
    expect(shortRate(SWISS_RATES, "rate-reduced", percents, "de-CH")).toBe("2.6%");
    expect(shortRate(SWISS_RATES, "", percents, "de-CH")).toBe("8.1%");
    expect(shortRate(SWISS_RATES, "rate-zero", percents, "de-CH")).toBe("0 % (steuerbar) (0%)");
    expect(shortRate(SWISS_RATES, "rate-wine", percents, "de-CH")).toBe("Weinbau");
    expect(shortRate(SWISS_RATES, PASS_THROUGH, percents, "de-CH")).toBeNull();
    // A hidden rate with the same percentage does not make the standard rate ambiguous,
    // but the hidden one names itself.
    expect(shortRate(SWISS_RATES, "rate-old", percents, "de-CH")).toBe("Alter Satz (8.1%)");
    expect(shortRate(SWISS_RATES, "rate-unknown", percents, "de-CH")).toBeNull();
  });
});
