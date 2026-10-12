import { describe, expect, it } from "vitest";

import { markItemsPaid } from "@/features/documents/paid-rows";

describe("markItemsPaid", () => {
  it("marks the given rows as paid and keeps the others", () => {
    const row = (id: string) => ({
      id,
      status: "issued",
      display_status: "overdue",
      open_amount: "10.00",
      number: id,
    });
    const [paid, other] = markItemsPaid([row("a"), row("b")], ["a"]);
    expect(paid).toEqual({
      id: "a",
      status: "paid",
      display_status: "paid",
      open_amount: "0.00",
      number: "a",
    });
    expect(other).toEqual(row("b"));
  });
});
