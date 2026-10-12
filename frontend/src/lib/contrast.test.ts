/// <reference types="node" />
// The test reads the real stylesheet so that the tokens have a single source of truth.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  contrastRatio,
  oklchToLinearSrgb,
  parseOklch,
  readCustomProperties,
  relativeLuminance,
} from "@/lib/contrast";

const css = readFileSync(resolve(process.cwd(), "src/styles/index.css"), "utf8");
const light = readCustomProperties(css, ":root");
const dark = { ...light, ...readCustomProperties(css, ".dark") };

const TEXT = 4.5;
const UI = 3;

/** [foreground token, background token, minimum ratio] – see principles.md 3.2. */
const PAIRS: readonly [string, string, number][] = [
  ["foreground", "background", TEXT],
  ["foreground", "card", TEXT],
  ["foreground", "popover", TEXT],
  ["foreground", "muted", TEXT],
  ["muted-foreground", "background", TEXT],
  ["muted-foreground", "card", TEXT],
  ["muted-foreground", "muted", TEXT],
  ["primary-foreground", "primary", TEXT],
  ["primary", "background", TEXT],
  ["primary", "card", TEXT],
  ["accent-foreground", "accent", TEXT],
  ["destructive-foreground", "destructive", TEXT],
  ["destructive", "background", TEXT],
  ["success", "background", TEXT],
  ["info", "background", TEXT],
  ["warning-foreground", "warning", TEXT],
  ["warning", "background", TEXT],
  ["ring", "background", UI],
  ["ring", "card", UI],
  ["input", "background", UI],
  ["input", "card", UI],
  // Filled fields: text and placeholder on the fill, bottom stroke against the fill.
  ["foreground", "field", TEXT],
  ["muted-foreground", "field", TEXT],
  ["foreground", "field-hover", TEXT],
  ["muted-foreground", "field-hover", TEXT],
  ["input", "field", UI],
  ["ring", "field", UI],
  // Chart marks (bars, comparison lines) next to each other on cards and the page.
  ["chart-1", "card", UI],
  ["chart-1", "background", UI],
  ["chart-2", "card", UI],
  ["chart-2", "background", UI],
  ["warning", "card", UI],
  ["destructive", "card", UI],
  ...[
    "draft",
    "sent",
    "issued",
    "partially-paid",
    "paid",
    "accepted",
    "overdue",
    "declined",
    "expired",
    "cancelled",
  ].flatMap((status): [string, string, number][] => [
    [`status-${status}-fg`, `status-${status}-bg`, TEXT],
    [`status-${status}-fg`, "background", TEXT],
    [`status-${status}-fg`, "card", TEXT],
  ]),
];

function colour(tokens: Record<string, string>, name: string, hue: number) {
  const variables = { ...tokens, "accent-hue": String(hue), "neutral-hue": String(hue) };
  let value = tokens[name];
  // Resolve token aliases such as "--card-foreground: var(--foreground)".
  while (value?.startsWith("var(--")) {
    value = tokens[value.slice(6, -1)];
  }
  if (value === undefined) throw new Error(`missing token --${name}`);
  return parseOklch(value, variables);
}

describe("design token contrast (WCAG 2.2 AA)", () => {
  const hues = Array.from({ length: 36 }, (_, index) => index * 10);
  for (const [mode, tokens] of [
    ["light", light],
    ["dark", dark],
  ] as const) {
    it.each(PAIRS)(`${mode}: %s on %s ≥ %d:1 for every accent hue`, (fg, bg, minimum) => {
      for (const hue of hues) {
        const ratio = contrastRatio(colour(tokens, fg, hue), colour(tokens, bg, hue));
        expect(ratio, `hue ${hue}`).toBeGreaterThanOrEqual(minimum);
      }
    });
  }
});

describe("contrast helpers", () => {
  it("computes the extremes correctly", () => {
    const white = parseOklch("oklch(1 0 0)", {});
    const black = parseOklch("oklch(0 0 0)", {});
    expect(relativeLuminance(white)).toBeCloseTo(1, 4);
    expect(relativeLuminance(black)).toBe(0);
    expect(contrastRatio(white, black)).toBeCloseTo(21, 2);
    expect(contrastRatio(black, white)).toBeCloseTo(21, 2);
  });

  it("clips out-of-gamut colours", () => {
    const [r, g, b] = oklchToLinearSrgb({ l: 0.7, c: 0.4, h: 30 });
    for (const channel of [r, g, b]) {
      expect(channel).toBeGreaterThanOrEqual(0);
      expect(channel).toBeLessThanOrEqual(1);
    }
  });

  it("parses alpha and variables", () => {
    expect(parseOklch("oklch(0.5 0.1 var(--h) / 0.5)", { h: "120" })).toEqual({
      l: 0.5,
      c: 0.1,
      h: 120,
    });
  });

  it("rejects unknown variables and non-oklch values", () => {
    expect(() => parseOklch("oklch(0.5 0.1 var(--missing))", {})).toThrow(
      "unknown variable --missing",
    );
    expect(() => parseOklch("#fff", {})).toThrow("not an oklch colour: #fff");
  });

  it("reads custom properties of a block", () => {
    expect(readCustomProperties(":root {\n  --a: 1;\n  --b-c: oklch(1 0 0);\n}", ":root")).toEqual({
      a: "1",
      "b-c": "oklch(1 0 0)",
    });
    expect(() => readCustomProperties("", ".missing")).toThrow("selector .missing not found");
  });
});
