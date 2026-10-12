import { describe, expect, it } from "vitest";

import { parseDecimal } from "@/lib/format/parse-decimal";

describe("parseDecimal", () => {
  it.each([
    // Swiss input
    ["de-CH", "1’234.50", "1234.50"],
    ["de-CH", "1'234.50", "1234.50"],
    ["de-CH", "1,234.5", "1234.5"],
    ["de-CH", "1,5", "1.5"],
    ["de-CH", "1,25", "1.25"],
    ["de-CH", "12,3456", "12.3456"],
    ["de-CH", "1,234", "1234"],
    ["de-CH", "1.234", "1.234"],
    ["de-CH", "1.234.567", "1234567"],
    ["de-CH", "1.234.567,89", "1234567.89"],
    ["de-CH", " 12 ", "12"],
    ["de-CH", ".5", "0.5"],
    ["de-CH", "5.", "5"],
    ["de-CH", "+3", "3"],
    ["de-CH", "-0.00", "0.00"],
    ["de-CH", "-1.5", "-1.5"],
    ["de-CH", "0007", "7"],
    ["de-CH", "000", "0"],
    // German and Austrian input
    ["de-DE", "1.234,50", "1234.50"],
    ["de-DE", "1.234", "1234"],
    ["de-DE", "1.5", "1.5"],
    ["de-DE", "1,5", "1.5"],
    ["de-DE", "1,234", "1.234"],
    ["de-DE", "1 234,5", "1234.5"],
    ["de-AT", "1\u00a0234,5", "1234.5"],
    ["de-AT", "0,5", "0.5"],
    ["de-AT", "-12,30", "-12.30"],
    // English input
    ["en", "1,234.5", "1234.5"],
    ["en", "1\u202f234", "1234"],
    ["en", "1,234,567", "1234567"],
  ] as const)("%s parses %j", (locale, input, expected) => {
    expect(parseDecimal(input, locale)).toBe(expected);
  });

  it.each([
    "",
    "   ",
    "abc",
    "1e5",
    "--1",
    "12a",
    ".",
    ",",
    "1.2.3",
    "1.234.56",
    "12.34.567",
    "1234.567,8",
    "1,234.5,6",
    "1.2,3.4",
    "-",
  ])("rejects %j", (input) => {
    expect(parseDecimal(input, "de-CH")).toBeNull();
  });
});
