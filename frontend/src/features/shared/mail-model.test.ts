import { describe, expect, it } from "vitest";

import { MAX_RECIPIENTS, parseRecipients, recipientProblem } from "@/features/shared/mail-model";

describe("mail recipients", () => {
  it("splits what was typed", () => {
    expect(parseRecipients(" a@example.com, b@example.com;c@example.com\nd@example.com ")).toEqual([
      "a@example.com",
      "b@example.com",
      "c@example.com",
      "d@example.com",
    ]);
    expect(parseRecipients("A@example.com, a@EXAMPLE.com")).toEqual(["A@example.com"]);
    expect(parseRecipients(" ,; ")).toEqual([]);
  });

  it("names what is wrong", () => {
    expect(recipientProblem([])).toEqual({ kind: "missing" });
    expect(recipientProblem(["a@example.com", "anna"])).toEqual({
      kind: "invalid",
      address: "anna",
    });
    const many = Array.from(
      { length: MAX_RECIPIENTS + 1 },
      (_, index) => `p${String(index)}@x.example`,
    );
    expect(recipientProblem(many)).toEqual({ kind: "tooMany" });
    expect(recipientProblem(many.slice(1))).toBeNull();
  });
});
