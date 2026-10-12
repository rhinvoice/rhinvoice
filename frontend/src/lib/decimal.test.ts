import { describe, expect, it } from "vitest";

import { addDecimals, compareDecimal } from "@/lib/decimal";

describe("compareDecimal", () => {
  it.each([
    ["1", "1.00", 0],
    ["297.8", "297.80", 0],
    ["297.81", "297.8", 1],
    ["0.1", "0.10000001", -1],
    ["-0.05", "0", -1],
    ["-1", "-2", 1],
    ["12345678901234567890.01", "12345678901234567890.02", -1],
  ] as const)("%s vs %s", (a, b, expected) => {
    expect(compareDecimal(a, b)).toBe(expected);
  });

  it("rejects other input", () => {
    expect(() => compareDecimal("1,5", "1")).toThrow("not a decimal: 1,5");
  });
});

describe("addDecimals", () => {
  it.each([
    [[], "0"],
    [["1659.50"], "1659.50"],
    [["1659.50", "0.5", "10"], "1670.00"],
    [["0.05", "-0.10"], "-0.05"],
    [["-1", "-2"], "-3"],
    [["12345678901234567890.01", "0.02"], "12345678901234567890.03"],
  ] as const)("%j", (values, expected) => {
    expect(addDecimals(values)).toBe(expected);
  });

  it("rejects other input", () => {
    expect(() => addDecimals(["1'000"])).toThrow("not a decimal: 1'000");
  });
});
