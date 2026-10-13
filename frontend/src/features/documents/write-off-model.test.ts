import { describe, expect, it } from "vitest";

import {
  canWriteOff,
  endOfInvoiceYear,
  isWriteOffDate,
  parseWriteOffEvent,
  paymentLimit,
} from "@/features/documents/write-off-model";

describe("endOfInvoiceYear", () => {
  it("is 31 December of the invoice's year", () => {
    expect(endOfInvoiceYear("2021-03-12", "2026-10-13")).toBe("2021-12-31");
    expect(endOfInvoiceYear("2025-12-31", "2026-01-01")).toBe("2025-12-31");
  });

  it("is today while the invoice's year is not over", () => {
    expect(endOfInvoiceYear("2026-02-01", "2026-10-13")).toBe("2026-10-13");
    expect(endOfInvoiceYear("2026-02-01", "2026-12-31")).toBe("2026-12-31");
  });
});

describe("isWriteOffDate", () => {
  it("accepts the days from the invoice date up to today", () => {
    expect(isWriteOffDate("2021-03-12", "2021-03-12", "2026-10-13")).toBe(true);
    expect(isWriteOffDate("2026-10-13", "2021-03-12", "2026-10-13")).toBe(true);
    expect(isWriteOffDate("2021-12-31", "2021-03-12", "2026-10-13")).toBe(true);
  });

  it("refuses days before the invoice and in the future", () => {
    expect(isWriteOffDate("2021-03-11", "2021-03-12", "2026-10-13")).toBe(false);
    expect(isWriteOffDate("2026-10-14", "2021-03-12", "2026-10-13")).toBe(false);
  });

  it("refuses what is no date", () => {
    expect(isWriteOffDate("", "2021-03-12", "2026-10-13")).toBe(false);
    expect(isWriteOffDate("31.12.2021", "2021-03-12", "2026-10-13")).toBe(false);
  });

  it("needs no invoice date", () => {
    expect(isWriteOffDate("2000-01-01", null, "2026-10-13")).toBe(true);
    expect(isWriteOffDate("2026-10-14", null, "2026-10-13")).toBe(false);
  });
});

describe("canWriteOff", () => {
  it("is for open invoices", () => {
    expect(canWriteOff({ type: "invoice", status: "issued" })).toBe(true);
    expect(canWriteOff({ type: "invoice", status: "partially_paid" })).toBe(true);
  });

  it("is not for paid, cancelled, written-off or draft invoices", () => {
    for (const status of ["draft", "paid", "cancelled", "written_off"] as const) {
      expect(canWriteOff({ type: "invoice", status })).toBe(false);
    }
  });

  it("is not for quotes and cancellation invoices", () => {
    expect(canWriteOff({ type: "quote", status: "sent" })).toBe(false);
    expect(canWriteOff({ type: "cancellation", status: "issued" })).toBe(false);
  });
});

describe("paymentLimit", () => {
  it("is the open amount of an open invoice", () => {
    expect(
      paymentLimit({ status: "partially_paid", open_amount: "659.50", written_off_amount: "0.00" }),
    ).toBe("659.50");
  });

  it("is what was written off of a written-off invoice", () => {
    expect(
      paymentLimit({ status: "written_off", open_amount: "0.00", written_off_amount: "559.50" }),
    ).toBe("559.50");
  });
});

describe("parseWriteOffEvent", () => {
  it("reads amount, date and reason", () => {
    expect(parseWriteOffEvent("2520.00 2021-12-31 gone")).toEqual({
      amount: "2520.00",
      date: "2021-12-31",
      reason: "gone",
    });
    expect(parseWriteOffEvent("20.00 2015-12-31 small_amount")?.reason).toBe("small_amount");
  });

  it("leaves other details alone", () => {
    expect(parseWriteOffEvent("")).toBeNull();
    expect(parseWriteOffEvent("2520.00")).toBeNull();
    expect(parseWriteOffEvent("2520.00 2021-12-31 bored")).toBeNull();
    expect(parseWriteOffEvent("2520 2021-12-31 gone")).toBeNull();
  });
});
