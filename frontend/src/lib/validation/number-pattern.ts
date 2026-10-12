/** Mirrors rhinvoice.domain.numbering.sequence.validate_pattern for instant feedback. */
export type PatternProblem = "length" | "placeholder" | "counter" | "characters" | "year";

const PLACEHOLDER = /\{([A-Z]+)\}/g;

export function patternProblem(pattern: string, yearlyReset: boolean): PatternProblem | null {
  if (pattern === "" || pattern.length > 40) return "length";
  const names = [...pattern.matchAll(PLACEHOLDER)].map((match) => String(match[1]));
  const isCounter = (name: string) => /^N+$/.test(name);
  if (names.some((name) => !["YYYY", "YY", "MM"].includes(name) && !isCounter(name))) {
    return "placeholder";
  }
  if (names.filter(isCounter).length !== 1) return "counter";
  const literals = pattern.split(/\{[A-Z]+\}/);
  if (!literals.every((literal) => /^[A-Za-z0-9\-_/.]*$/.test(literal))) return "characters";
  if (yearlyReset && !names.some((name) => name === "YYYY" || name === "YY")) return "year";
  return null;
}
