import { describe, expect, it } from "vitest";

import {
  currentIndex,
  emptyTaxRate,
  formToRequest,
  percentProblem,
  rateSubline,
  sourceLink,
  taxRateFieldFor,
  taxRateSchema,
  taxRateToForm,
  todayPercent,
  withValue,
  type TaxRateFormValues,
} from "@/features/tax-rates/tax-rate-form-model";
import { translatorFor } from "@/lib/i18n";
import { SWISS_RATES, taxRate } from "@/test/tax-rates";

const t = translatorFor("de-CH");
const schema = taxRateSchema(t, "de-CH");
const TODAY = "2026-11-12";

function issues(values: TaxRateFormValues): Record<string, string> {
  const result = schema.safeParse(values);
  if (result.success) return {};
  return Object.fromEntries(
    result.error.issues.map((issue) => [issue.path.join("."), issue.message]),
  );
}

function rateAt(index: number) {
  const rate = SWISS_RATES[index];
  if (rate === undefined) throw new Error(`no rate ${String(index)} in the fixture`);
  return rate;
}

const valid: TaxRateFormValues = {
  name: "Landwirtschaft",
  category: "S",
  values: [{ valid_from: "2025-01-01", percent: "7.8" }],
  exemption_reason: "",
  notice: "",
};

describe("tax rate form", () => {
  it("starts a new rate as taxable from the start of the year", () => {
    expect(emptyTaxRate(TODAY)).toEqual({
      name: "",
      category: "S",
      values: [{ valid_from: "2026-01-01", percent: "" }],
      exemption_reason: "",
      notice: "",
    });
  });

  it("checks name, percentage and date", () => {
    expect(issues(valid)).toEqual({});
    expect(issues({ ...valid, name: " ", values: [{ valid_from: "", percent: "" }] })).toEqual({
      name: "Bitte ausfüllen.",
      "values.0.valid_from": "Bitte ausfüllen.",
      "values.0.percent": "Bitte ausfüllen.",
    });
    expect(issues({ ...valid, values: [{ valid_from: "2025-01-01", percent: "7.825" }] })).toEqual({
      "values.0.percent": "Höchstens 2 Nachkommastellen.",
    });
    expect(
      Object.keys(issues({ ...valid, values: [{ valid_from: "2025-01-01", percent: "100" }] })),
    ).toEqual(["values.0.percent"]);
  });

  it("checks the category against the percentages as EN 16931 does", () => {
    expect(issues({ ...valid, values: [{ valid_from: "2025-01-01", percent: "0" }] })).toEqual({
      "values.0.percent": "Steuerpflichtig (S) braucht einen Prozentsatz über 0 %.",
    });
    expect(
      issues({
        ...valid,
        category: "Z",
        values: [
          { valid_from: "2024-01-01", percent: "0" },
          { valid_from: "2025-01-01", percent: "2.5" },
        ],
      }),
    ).toEqual({ "values.1.percent": "Nullsatz (Z) und Steuerfrei (E) brauchen 0 %." });
    expect(
      issues({ ...valid, category: "E", values: [{ valid_from: "2025-01-01", percent: "0" }] }),
    ).toEqual({ exemption_reason: "Steuerfrei (E) braucht einen Befreiungsgrund." });
    expect(
      issues({
        ...valid,
        category: "E",
        exemption_reason: "§ 4 UStG",
        values: [{ valid_from: "2025-01-01", percent: "0" }],
      }),
    ).toEqual({});
  });

  it("names the problem of a percentage for a category", () => {
    expect(percentProblem("S", "8,1", "de-DE", t)).toBeNull();
    expect(percentProblem("S", "0", "de-CH", t)).toBe(
      "Steuerpflichtig (S) braucht einen Prozentsatz über 0 %.",
    );
    expect(percentProblem("Z", "0.00", "de-CH", t)).toBeNull();
    expect(percentProblem("E", "1", "de-CH", t)).toBe(
      "Nullsatz (Z) und Steuerfrei (E) brauchen 0 %.",
    );
    expect(percentProblem("S", "abc", "de-CH", t)).toBeNull();
  });

  it("converts a rate for editing and back", () => {
    const form = taxRateToForm(rateAt(0), "de-DE");
    expect(form.values).toEqual([
      { valid_from: "2018-01-01", percent: "7,7" },
      { valid_from: "2024-01-01", percent: "8,1" },
    ]);
    expect(formToRequest(form, "de-DE")).toEqual({
      name: "Normalsatz",
      category: "S",
      values: [
        { valid_from: "2018-01-01", percent: "7.7" },
        { valid_from: "2024-01-01", percent: "8.1" },
      ],
      exemption_reason: "",
      notice: "",
    });
    // Only an exempt rate names its reason.
    expect(formToRequest(taxRateToForm(rateAt(3), "de-CH"), "de-CH").exemption_reason).toBe(
      "Steuerbefreite Leistung",
    );
    expect(
      formToRequest({ ...form, exemption_reason: "left over" }, "de-DE").exemption_reason,
    ).toBe("");
  });

  it("shows the value in force today, else the first to come", () => {
    const values = [{ valid_from: "2018-01-01" }, { valid_from: "2024-01-01" }];
    expect(currentIndex(values, TODAY)).toBe(1);
    expect(currentIndex(values, "2020-01-01")).toBe(0);
    expect(currentIndex([{ valid_from: "2030-01-01" }], TODAY)).toBe(0);
  });

  it("adds a value from a date, replacing one on the same date", () => {
    const values = [
      { valid_from: "2018-01-01", percent: "7.7" },
      { valid_from: "2024-01-01", percent: "8.1" },
    ];
    expect(withValue(values, { valid_from: "2020-01-01", percent: "7.9" })).toEqual([
      values[0],
      { valid_from: "2020-01-01", percent: "7.9" },
      values[1],
    ]);
    expect(withValue(values, { valid_from: "2024-01-01", percent: "8.2" })).toEqual([
      values[0],
      { valid_from: "2024-01-01", percent: "8.2" },
    ]);
  });

  it("sums a rate up below its name", () => {
    expect(rateSubline(rateAt(0), TODAY, "de-CH", t)).toBe("seit 01.01.2024 · vorher 7.7%");
    expect(rateSubline(rateAt(2), TODAY, "de-CH", t)).toBe("");
    expect(rateSubline(rateAt(3), TODAY, "de-CH", t)).toBe("Grund: Steuerbefreite Leistung");
    expect(rateSubline(rateAt(5), TODAY, "de-CH", t)).toBe("ab 01.01.2030: 5% · Eigener Hinweis");
    const rising = taxRate({
      id: "r",
      name: "Steigend",
      values: [
        { valid_from: "2024-01-01", percent: "8.1" },
        { valid_from: "2027-01-01", percent: "8.5" },
      ],
    });
    expect(rateSubline(rising, TODAY, "de-CH", t)).toBe("ab 01.01.2027: 8.5%");
  });

  it("shows today's percentage, a dash before the first", () => {
    expect(todayPercent(rateAt(0), TODAY, "de-CH")).toBe("8.1%");
    expect(todayPercent(rateAt(5), TODAY, "de-CH")).toBe("–");
  });

  it("links the sources of a preset", () => {
    expect(
      sourceLink("https://www.gesetze-im-internet.de/ustg_1980/__24.html (Abs. 1 Satz 4)"),
    ).toEqual({
      url: "https://www.gesetze-im-internet.de/ustg_1980/__24.html",
      note: "(Abs. 1 Satz 4)",
    });
    expect(sourceLink("https://www.estv.admin.ch")).toEqual({
      url: "https://www.estv.admin.ch",
      note: "",
    });
    expect(sourceLink("BGBl. 2024 I Nr. 387")).toEqual({ url: null, note: "BGBl. 2024 I Nr. 387" });
  });

  it("maps API error fields", () => {
    expect(taxRateFieldFor("name")).toBe("name");
    expect(taxRateFieldFor("exemption_reason")).toBe("exemption_reason");
    expect(taxRateFieldFor("values.1.percent")).toBe("values.1.percent");
    expect(taxRateFieldFor("values.0.valid_from")).toBe("values.0.valid_from");
    expect(taxRateFieldFor("values")).toBeNull();
    expect(taxRateFieldFor("hidden")).toBeNull();
  });
});
