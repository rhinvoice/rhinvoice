import type { Unit } from "@/features/shared/units-api";

/** An entry of a unit select: the unit's id and its label. */
export interface UnitOption {
  readonly value: string;
  readonly label: string;
  /** Hidden units appear only where they are chosen already (ADR 0046). */
  readonly hidden: boolean;
}

/**
 * The units a select offers, in the company's order: those not hidden, and the ``current``
 * one where it is hidden (a line, article or plan keeps it).
 */
export function unitOptions(units: readonly Unit[], current: string): UnitOption[] {
  return units
    .filter((unit) => !unit.hidden || unit.id === current)
    .map((unit) => ({ value: unit.id, label: unit.label, hidden: unit.hidden }));
}

/** The unit of new lines and articles: the first one offered, "" while none is known. */
export function defaultUnitId(units: readonly Unit[] | undefined): string {
  return units?.find((unit) => !unit.hidden)?.id ?? "";
}

/** The label of a unit by its id; "" for none or one not known (yet). */
export function unitLabelOf(units: readonly Unit[] | undefined, id: string | null): string {
  return units?.find((unit) => unit.id === id)?.label ?? "";
}
