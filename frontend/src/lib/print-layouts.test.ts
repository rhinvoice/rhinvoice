import { describe, expect, it } from "vitest";

import { layoutFor } from "@/lib/print-layouts";

const STANDARD = { id: "s", is_default: true };
const TRUST = { id: "t", is_default: false };
const PLAIN = { id: "p", is_default: false };
const LAYOUTS = [TRUST, STANDARD, PLAIN];

describe("the layout of a document", () => {
  it("is its own, else its customer's, else the default", () => {
    expect(layoutFor(LAYOUTS, "p", "t")).toBe(PLAIN);
    expect(layoutFor(LAYOUTS, null, "t")).toBe(TRUST);
    expect(layoutFor(LAYOUTS, null, null)).toBe(STANDARD);
  });

  it("skips deleted choices", () => {
    expect(layoutFor(LAYOUTS, "gone", "t")).toBe(TRUST);
    expect(layoutFor(LAYOUTS, "gone", "gone")).toBe(STANDARD);
    expect(layoutFor<typeof STANDARD>([], null, null)).toBeUndefined();
  });
});
