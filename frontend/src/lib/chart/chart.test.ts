import { describe, expect, it } from "vitest";

import { barLayout, niceScale, sparkline } from "@/lib/chart";

describe("barLayout", () => {
  it("scales positive values to the largest one", () => {
    expect(barLayout(["50.00", "100.00", "0.00"])).toEqual({
      zero: 1,
      bars: [
        { top: 0.5, height: 0.5, negative: false },
        { top: 0, height: 1, negative: false },
        { top: 1, height: 0, negative: false },
      ],
    });
  });

  it("draws negative values below the zero line", () => {
    expect(barLayout(["300", "-100"])).toEqual({
      zero: 0.75,
      bars: [
        { top: 0, height: 0.75, negative: false },
        { top: 0.75, height: 0.25, negative: true },
      ],
    });
  });

  it("puts the zero line at the top when everything is negative", () => {
    expect(barLayout(["-20"])).toEqual({
      zero: 0,
      bars: [{ top: 0, height: 1, negative: true }],
    });
  });

  it("handles empty and all-zero series", () => {
    expect(barLayout([])).toEqual({ zero: 1, bars: [] });
    expect(barLayout(["0", "0.00"])).toEqual({
      zero: 1,
      bars: [
        { top: 1, height: 0, negative: false },
        { top: 1, height: 0, negative: false },
      ],
    });
  });
});

describe("niceScale", () => {
  it.each([
    [9400, { max: 10000, ticks: [0, 2500, 5000, 7500, 10000] }],
    [18900, { max: 20000, ticks: [0, 5000, 10000, 15000, 20000] }],
    [100, { max: 100, ticks: [0, 25, 50, 75, 100] }],
    [1, { max: 1, ticks: [0, 0.25, 0.5, 0.75, 1] }],
    [7, { max: 8, ticks: [0, 2, 4, 6, 8] }],
    [4, { max: 4, ticks: [0, 1, 2, 3, 4] }],
    [0, { max: 1, ticks: [0, 1] }],
    [-5, { max: 1, ticks: [0, 1] }],
    [Number.NaN, { max: 1, ticks: [0, 1] }],
  ])("%s", (largest, expected) => {
    expect(niceScale(largest)).toEqual(expected);
  });

  it("takes the next power of ten when no factor fits", () => {
    expect(niceScale(95, 1)).toEqual({ max: 100, ticks: [0, 100] });
  });
});

describe("sparkline", () => {
  it("scales between the lowest and the highest value", () => {
    expect(sparkline([0, 10, 5], 100, 30)).toEqual({
      line: "M0,27L50,3L100,15",
      area: "M0,27L50,3L100,15L100,30L0,30Z",
      end: [100, 15],
    });
  });

  it("draws a flat line in the middle and copes with one value", () => {
    expect(sparkline([4, 4], 10, 20).line).toBe("M0,10L10,10");
    expect(sparkline([4], 10, 20)).toEqual({
      line: "M0,10",
      area: "M0,10L0,20L0,20Z",
      end: [0, 10],
    });
    expect(sparkline([], 10, 20)).toEqual({ line: "", area: "L0,20L0,20Z", end: [0, 20] });
  });
});
