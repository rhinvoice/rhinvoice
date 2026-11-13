import { describe, expect, it } from "vitest";

import { PASS_THROUGH } from "@/features/shared/tax-rate-model";

import {
  inTotalChoice,
  inTotalTag,
  orphanedAlternatives,
  parseInTotalChoice,
  positionNumbers,
  replaceableLines,
  type MarkedLine,
} from "@/features/documents/in-total-model";

const line = (key: string, marks: Partial<MarkedLine> = {}): MarkedLine => ({
  key,
  kind: "item",
  in_total: "yes",
  alternative_to: null,
  tax: "",
  description: key,
  ...marks,
});

const DESIGN = line("design");
const LARGE = line("large", { in_total: "alternative", alternative_to: "small" });
const EXTRA = line("extra", { in_total: "optional" });
const FEES = line("fees", { tax: PASS_THROUGH });
const OFFER = [line("heading", { kind: "text" }), DESIGN, FEES, line("small"), LARGE, EXTRA];

describe("the In total choice", () => {
  it("reads and writes the select's value", () => {
    expect(inTotalChoice(DESIGN)).toBe("yes");
    expect(inTotalChoice(LARGE)).toBe("alternative:small");
    expect(inTotalChoice(EXTRA)).toBe("optional");
    // An alternative that lost its line reads as optional.
    expect(inTotalChoice(line("x", { in_total: "alternative" }))).toBe("optional");
    expect(parseInTotalChoice("yes")).toEqual({ in_total: "yes", alternative_to: null });
    expect(parseInTotalChoice("optional")).toEqual({ in_total: "optional", alternative_to: null });
    expect(parseInTotalChoice("alternative:small")).toEqual({
      in_total: "alternative",
      alternative_to: "small",
    });
  });

  it("numbers the positions as the PDF prints them", () => {
    // Neither the heading nor the pass-through fees have a number.
    expect([...positionNumbers(OFFER)]).toEqual([
      ["design", 1],
      ["small", 2],
      ["large", 3],
      ["extra", 4],
    ]);
  });

  it("offers every other item in the total to replace", () => {
    expect(replaceableLines(OFFER, 4)).toEqual([
      { key: "design", number: 1, description: "design" },
      { key: "fees", number: null, description: "fees" },
      { key: "small", number: 2, description: "small" },
    ]);
    expect(replaceableLines(OFFER, 3)).toEqual([
      { key: "design", number: 1, description: "design" },
      { key: "fees", number: null, description: "fees" },
    ]);
  });

  it("finds the alternatives whose line is gone or no longer counts", () => {
    expect(orphanedAlternatives(OFFER)).toEqual([]);
    const changed = [
      ...OFFER.slice(0, 3),
      line("small", { in_total: "optional" }),
      ...OFFER.slice(4),
      line("lost", { in_total: "alternative" }),
      line("text", { in_total: "alternative", alternative_to: "heading" }),
    ];
    expect(orphanedAlternatives(changed)).toEqual([4, 6, 7]);
    expect(orphanedAlternatives(OFFER.filter((each) => each.key !== "small"))).toEqual([3]);
  });

  it("tags closed lines outside the total", () => {
    expect(inTotalTag(OFFER, 1)).toBeNull();
    expect(inTotalTag(OFFER, 9)).toBeNull();
    expect(inTotalTag(OFFER, 5)).toEqual({ kind: "optional" });
    // The number of the replaced position as printed, not the row in the editor.
    expect(inTotalTag(OFFER, 4)).toEqual({ kind: "alternative", number: 2 });
    // Pass-through items have no number to name.
    expect(
      inTotalTag([FEES, line("x", { in_total: "alternative", alternative_to: "fees" })], 1),
    ).toEqual({ kind: "alternative", number: null });
    expect(inTotalTag([line("x", { in_total: "alternative" })], 0)).toEqual({
      kind: "alternative",
      number: null,
    });
    expect(inTotalTag([line("lost", { in_total: "alternative", alternative_to: "x" })], 0)).toEqual(
      { kind: "alternative", number: null },
    );
  });
});
