/**
 * Optional and alternative items of quotes (ADR 0045): they keep their amount but stay out of
 * the total. An alternative replaces another item of the same quote that counts itself.
 */

import { PASS_THROUGH } from "@/features/shared/tax-rate-model";

export const IN_TOTAL = ["yes", "optional", "alternative"] as const;
export type InTotal = (typeof IN_TOTAL)[number];

/** What the helpers read of a line of the form; ``alternative_to`` is the replaced line's key. */
export interface MarkedLine {
  readonly key: string;
  readonly kind: "item" | "text";
  readonly in_total: InTotal;
  readonly alternative_to: string | null;
  /** The tax choice of the line; pass-through items have no position number. */
  readonly tax: string;
  readonly description: string;
}

const ALTERNATIVE_PREFIX = "alternative:";

/** The value of the "In total" select: "yes", "optional" or "alternative:" and a line's key. */
export function inTotalChoice(line: Pick<MarkedLine, "in_total" | "alternative_to">): string {
  if (line.in_total === "alternative" && line.alternative_to !== null) {
    return `${ALTERNATIVE_PREFIX}${line.alternative_to}`;
  }
  return line.in_total === "yes" ? "yes" : "optional";
}

/** The marks a value of the "In total" select stands for. */
export function parseInTotalChoice(value: string): Pick<MarkedLine, "in_total" | "alternative_to"> {
  if (value.startsWith(ALTERNATIVE_PREFIX)) {
    return { in_total: "alternative", alternative_to: value.slice(ALTERNATIVE_PREFIX.length) };
  }
  return { in_total: value === "optional" ? "optional" : "yes", alternative_to: null };
}

const counts = (line: MarkedLine) => line.kind === "item" && line.in_total === "yes";

/**
 * The number of each position as the PDF prints it: items only, without text lines and
 * pass-through items, which the PDF lists in their own block.
 */
export function positionNumbers(lines: readonly MarkedLine[]): ReadonlyMap<string, number> {
  const printed = lines.filter((line) => line.kind === "item" && line.tax !== PASS_THROUGH);
  return new Map(printed.map((line, at) => [line.key, at + 1]));
}

/** A line an alternative can replace; ``number`` is null for one without a position number. */
export interface ReplaceableLine {
  readonly key: string;
  readonly number: number | null;
  readonly description: string;
}

/** The lines an item at ``index`` can replace: every other item that counts. */
export function replaceableLines(lines: readonly MarkedLine[], index: number): ReplaceableLine[] {
  const numbers = positionNumbers(lines);
  return lines.flatMap((line, at) =>
    at !== index && counts(line)
      ? [{ key: line.key, number: numbers.get(line.key) ?? null, description: line.description }]
      : [],
  );
}

/** The alternatives whose line is gone or no longer counts; they become optional. */
export function orphanedAlternatives(lines: readonly MarkedLine[]): number[] {
  const counted = new Set(lines.filter(counts).map((line) => line.key));
  return lines.flatMap((line, index) =>
    line.in_total === "alternative" &&
    (line.alternative_to === null || !counted.has(line.alternative_to))
      ? [index]
      : [],
  );
}

/** What a closed line says about its place in the total: nothing, optional or an alternative. */
export type InTotalTag =
  | { readonly kind: "optional" }
  | { readonly kind: "alternative"; readonly number: number | null }
  | null;

/** The tag of the line at ``index``; an alternative names the position it replaces, as printed. */
export function inTotalTag(lines: readonly MarkedLine[], index: number): InTotalTag {
  const line = lines[index];
  if (line === undefined || line.in_total === "yes") return null;
  if (line.in_total === "optional") return { kind: "optional" };
  const number =
    line.alternative_to === null ? undefined : positionNumbers(lines).get(line.alternative_to);
  return { kind: "alternative", number: number ?? null };
}
