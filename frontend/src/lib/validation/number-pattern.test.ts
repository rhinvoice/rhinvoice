import { describe, expect, it } from "vitest";

import { patternProblem } from "@/lib/validation/number-pattern";

describe("patternProblem", () => {
  it.each(["R{YYYY}{NNNN}", "RE/{YY}.{MM}-{NNNN}_x", "{N}"])("accepts %s", (pattern) => {
    expect(patternProblem(pattern, pattern.includes("Y"))).toBeNull();
  });

  it.each([
    ["", false, "length"],
    [`{N}${"x".repeat(38)}`, false, "length"],
    ["{DD}{NNN}", false, "placeholder"],
    ["R{YYYY}", false, "counter"],
    ["{NN}{NNN}", false, "counter"],
    ["R {NNN}", false, "characters"],
    ["{YY}-{NNN} x{MM}", false, "characters"],
    ["{NNNN}", true, "year"],
  ] as const)("reports %j (reset %s) as %s", (pattern, reset, problem) => {
    expect(patternProblem(pattern, reset)).toBe(problem);
  });
});
