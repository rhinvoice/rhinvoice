import { describe, expect, it } from "vitest";

import {
  levelProblems,
  toInput,
  toRequest,
  type LevelInput,
} from "@/features/dunning/dunning-levels-model";

const LEVEL = {
  level: 1,
  days_after_due: 7,
  payment_days: 10,
  fee: "0.00",
  text_de: "Bitte",
  text_en: "Please",
  text_fr: "Veuillez",
  text_it: "Vi preghiamo",
};

function input(overrides: Partial<LevelInput>): LevelInput {
  return { ...toInput(LEVEL), ...overrides };
}

describe("dunning levels", () => {
  it("round-trip as typed text", () => {
    expect(toInput(LEVEL)).toEqual({ ...LEVEL, days_after_due: "7", payment_days: "10" });
    expect(toRequest(input({ fee: "12,5", days_after_due: " 0 " }))).toEqual({
      ...LEVEL,
      days_after_due: 0,
      fee: "12.50",
    });
  });

  it("name every field that is wrong", () => {
    expect(levelProblems([input({})])).toEqual(new Map());
    expect(
      levelProblems([input({ days_after_due: "365", payment_days: "1", fee: "1000" })]),
    ).toEqual(new Map());
    const problems = levelProblems([
      input({}),
      input({
        days_after_due: "",
        payment_days: "0",
        fee: "12.33",
        text_de: "x".repeat(2001),
        text_en: "x".repeat(2001),
        text_fr: "x".repeat(2001),
        text_it: "x".repeat(2001),
      }),
      input({ days_after_due: "366", payment_days: "1e2", fee: "1000.05" }),
    ]);
    expect(Object.fromEntries(problems)).toEqual({
      "1.days_after_due": "days",
      "1.payment_days": "paymentDays",
      "1.fee": "fee",
      "1.text_de": "text",
      "1.text_en": "text",
      "1.text_fr": "text",
      "1.text_it": "text",
      "2.days_after_due": "days",
      "2.payment_days": "paymentDays",
      "2.fee": "fee",
    });
  });

  it("refuse fees that are no amount", () => {
    expect(levelProblems([input({ fee: "abc" })]).get("0.fee")).toBe("fee");
    expect(levelProblems([input({ fee: "-5" })]).get("0.fee")).toBe("fee");
    expect(toRequest(input({ fee: "abc" })).fee).toBe("0.00");
  });
});
