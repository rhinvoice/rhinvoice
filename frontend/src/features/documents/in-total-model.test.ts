import { describe, expect, it } from "vitest";

import {
  inTotalChoice,
  inTotalTag,
  orphanedAlternatives,
  parseInTotalChoice,
  replaceableLines,
  type MarkedLine,
} from "@/features/documents/in-total-model";

const line = (key: string, marks: Partial<MarkedLine> = {}): MarkedLine => ({
  key,
  kind: "item",
  in_total: "yes",
  alternative_to: null,
  ...marks,
});

const DESIGN = line("design");
const LARGE = line("large", { in_total: "alternative", alternative_to: "small" });
const EXTRA = line("extra", { in_total: "optional" });
const OFFER = [line("heading", { kind: "text" }), DESIGN, line("small"), LARGE, EXTRA];

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

  it("offers every other item in the total to replace", () => {
    expect(replaceableLines(OFFER, 3)).toEqual([
      { key: "design", number: 2 },
      { key: "small", number: 3 },
    ]);
    expect(replaceableLines(OFFER, 2)).toEqual([{ key: "design", number: 2 }]);
  });

  it("finds the alternatives whose line is gone or no longer counts", () => {
    expect(orphanedAlternatives(OFFER)).toEqual([]);
    const changed = [
      ...OFFER.slice(0, 2),
      line("small", { in_total: "optional" }),
      ...OFFER.slice(3),
      line("lost", { in_total: "alternative" }),
      line("text", { in_total: "alternative", alternative_to: "heading" }),
    ];
    expect(orphanedAlternatives(changed)).toEqual([3, 5, 6]);
    expect(orphanedAlternatives(OFFER.filter((each) => each.key !== "small"))).toEqual([2]);
  });

  it("tags closed lines outside the total", () => {
    expect(inTotalTag(OFFER, 1)).toBeNull();
    expect(inTotalTag(OFFER, 9)).toBeNull();
    expect(inTotalTag(OFFER, 4)).toEqual({ kind: "optional" });
    expect(inTotalTag(OFFER, 3)).toEqual({ kind: "alternative", number: 3 });
    expect(inTotalTag([line("lost", { in_total: "alternative", alternative_to: "x" })], 0)).toEqual(
      { kind: "alternative", number: null },
    );
  });
});
