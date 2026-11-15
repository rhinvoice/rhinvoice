import { describe, expect, it } from "vitest";

import { defaultUnitId, unitLabelOf, unitOptions } from "@/features/shared/unit-model";
import { UNITS } from "@/test/units";

describe("unit selects", () => {
  it("offer the units in their order without the hidden ones", () => {
    expect(unitOptions(UNITS, "unit-hours")).toEqual([
      { value: "unit-pieces", label: "Stk.", hidden: false },
      { value: "unit-hours", label: "Std.", hidden: false },
      { value: "unit-quintal", label: "dz", hidden: false },
    ]);
  });

  it("keep a hidden unit where it is chosen", () => {
    expect(unitOptions(UNITS, "unit-minutes").map((option) => option.value)).toEqual([
      "unit-pieces",
      "unit-hours",
      "unit-minutes",
      "unit-quintal",
    ]);
    expect(unitOptions(UNITS, "unit-minutes")[2]).toEqual({
      value: "unit-minutes",
      label: "Min.",
      hidden: true,
    });
  });

  it("take the first unit offered for new lines and articles", () => {
    expect(defaultUnitId(UNITS)).toBe("unit-pieces");
    const hidden = UNITS.map((unit) => ({ ...unit, hidden: unit.code === "C62" }));
    expect(defaultUnitId(hidden)).toBe("unit-hours");
    expect(defaultUnitId(UNITS.map((unit) => ({ ...unit, hidden: true })))).toBe("");
    expect(defaultUnitId(undefined)).toBe("");
  });

  it("name a unit by its label", () => {
    expect(unitLabelOf(UNITS, "unit-quintal")).toBe("dz");
    expect(unitLabelOf(UNITS, null)).toBe("");
    expect(unitLabelOf(UNITS, "gone")).toBe("");
    expect(unitLabelOf(undefined, "unit-quintal")).toBe("");
  });
});
