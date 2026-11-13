/**
 * Optional and alternative items of quotes (ADR 0045): they keep their amount but stay out of
 * the total. An alternative replaces another item of the same quote that counts itself.
 */

export const IN_TOTAL = ["yes", "optional", "alternative"] as const;
export type InTotal = (typeof IN_TOTAL)[number];

/** What the helpers read of a line of the form; ``alternative_to`` is the replaced line's key. */
export interface MarkedLine {
  readonly key: string;
  readonly kind: "item" | "text";
  readonly in_total: InTotal;
  readonly alternative_to: string | null;
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

/** The lines an item at ``index`` can replace: every other item that counts, with its number. */
export function replaceableLines(
  lines: readonly MarkedLine[],
  index: number,
): { readonly key: string; readonly number: number }[] {
  return lines.flatMap((line, at) =>
    at !== index && counts(line) ? [{ key: line.key, number: at + 1 }] : [],
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

/** The tag of the line at ``index``; an alternative names the number of the line it replaces. */
export function inTotalTag(lines: readonly MarkedLine[], index: number): InTotalTag {
  const line = lines[index];
  if (line === undefined || line.in_total === "yes") return null;
  if (line.in_total === "optional") return { kind: "optional" };
  const at = lines.findIndex((other) => other.key === line.alternative_to);
  return { kind: "alternative", number: at < 0 ? null : at + 1 };
}
