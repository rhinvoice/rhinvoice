import type { Unit } from "@/features/shared/units-api";

function unit(overrides: Partial<Unit> & Pick<Unit, "id" | "code" | "label">): Unit {
  return {
    labels: { en: "", fr: "", it: "" },
    description: "",
    preset: overrides.code,
    hidden: false,
    in_use: false,
    ...overrides,
  };
}

/** Units as the API sends them (GET /api/units): pieces, hours, a hidden one and dz. */
export const UNITS: readonly Unit[] = [
  unit({
    id: "unit-pieces",
    code: "C62",
    label: "Stk.",
    labels: { en: "pcs", fr: "pce", it: "pz." },
  }),
  unit({ id: "unit-hours", code: "HUR", label: "Std.", labels: { en: "h", fr: "h", it: "h" } }),
  unit({ id: "unit-minutes", code: "MIN", label: "Min.", hidden: true, in_use: true }),
  unit({
    id: "unit-quintal",
    code: "DTN",
    label: "dz",
    labels: { en: "dt", fr: "q", it: "q" },
    description: "Doppelzentner (100 kg)",
  }),
];

export function unitAt(index: number): Unit {
  const found = UNITS[index];
  if (found === undefined) throw new Error(`no unit ${String(index)} in the fixture`);
  return found;
}
