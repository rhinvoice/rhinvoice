import { describe, expect, it } from "vitest";

import type { Dashboard } from "@/features/dashboard/api";
import {
  acceptanceRate,
  ageParts,
  dashboardCurrencies,
  recentMonths,
  yearChange,
  yearComparison,
} from "@/features/dashboard/dashboard-model";

const EMPTY: Dashboard = {
  figures: [],
  revenue: [],
  recent: [],
  aging: [],
  expected: [],
  overdue: [],
  quotes: [],
  top_customers: [],
  days_to_pay: [],
  today: "2026-03-09",
  currency: null,
  year_to_date: [],
};

function figure(currency: "CHF" | "EUR"): Dashboard["figures"][number] {
  return {
    currency,
    open: "0.00",
    overdue: "0.00",
    paid: "0.00",
    open_count: 0,
    overdue_count: 0,
  };
}

const REVENUE: Dashboard["revenue"] = [
  { month: "2025-01-01", currency: "CHF", net: "100.00" },
  { month: "2025-02-01", currency: "CHF", net: "200.00" },
  { month: "2025-03-01", currency: "CHF", net: "300.00" },
  { month: "2025-12-01", currency: "CHF", net: "900.00" },
  { month: "2026-01-01", currency: "CHF", net: "150.00" },
  { month: "2026-03-01", currency: "CHF", net: "-50.00" },
  { month: "2026-03-01", currency: "EUR", net: "70.00" },
];

describe("dashboardCurrencies", () => {
  it("lists the currencies with figures first, then the others once", () => {
    expect(dashboardCurrencies(EMPTY)).toEqual([]);
    expect(
      dashboardCurrencies({
        ...EMPTY,
        figures: [figure("EUR")],
        revenue: REVENUE,
        quotes: [{ currency: "CHF", open: "1.00", open_count: 1, accepted: 0, decided: 0 }],
        aging: [{ currency: "EUR", not_due: "1", late_30: "0", late_60: "0", late_more: "0" }],
      }),
    ).toEqual(["EUR", "CHF"]);
  });

  it("puts the company's currency first, also before its first invoice", () => {
    // An Austrian company with a Swiss franc quote: euros first.
    const austrian = {
      ...EMPTY,
      currency: "EUR" as const,
      quotes: [{ currency: "CHF" as const, open: "1.00", open_count: 1, accepted: 0, decided: 0 }],
    };
    expect(dashboardCurrencies(austrian)).toEqual(["EUR", "CHF"]);
    expect(dashboardCurrencies({ ...austrian, figures: [figure("CHF")] })).toEqual(["EUR", "CHF"]);
    expect(dashboardCurrencies({ ...EMPTY, currency: "EUR" })).toEqual(["EUR"]);
  });
});

describe("yearComparison", () => {
  it("lays this year's months next to last year's", () => {
    const comparison = yearComparison(REVENUE, "CHF", "2026-03-09");
    expect(comparison.months).toHaveLength(12);
    expect(comparison.months[0]).toBe("2026-01-01");
    expect(comparison.months[11]).toBe("2026-12-01");
    expect(comparison.current).toEqual([150, 0, -50, ...Array<null>(9).fill(null)]);
    expect(comparison.previous).toEqual([100, 200, 300, 0, 0, 0, 0, 0, 0, 0, 0, 900]);
    const december = yearComparison(REVENUE, "EUR", "2026-12-31");
    expect(december.current.every((value) => value !== null)).toBe(true);
  });
});

describe("yearChange", () => {
  it("is the change against last year up to the same day", () => {
    expect(yearChange("112.00", "100.00")).toBeCloseTo(0.12);
    expect(yearChange("50.00", "100.00")).toBe(-0.5);
    expect(yearChange("50.00", "0.00")).toBeNull();
    expect(yearChange("50.00", "-10.00")).toBeNull();
  });
});

describe("recentMonths", () => {
  it("lists the last months up to today's, oldest first", () => {
    expect(recentMonths(REVENUE, "CHF", "2026-03-09", 4)).toEqual([900, 150, 0, -50]);
    expect(recentMonths(REVENUE, "CHF", "2026-03-09")).toHaveLength(12);
  });
});

describe("acceptanceRate", () => {
  it("is the share of the decided quotes", () => {
    expect(acceptanceRate(2, 4)).toBe(0.5);
    expect(acceptanceRate(0, 0)).toBeNull();
  });
});

describe("ageParts", () => {
  it("splits the open invoices by age", () => {
    expect(
      ageParts({
        currency: "CHF",
        not_due: "75.00",
        late_30: "0.00",
        late_60: "20.00",
        late_more: "5.00",
      }),
    ).toEqual([
      { key: "not_due", amount: "75.00", share: 0.75 },
      { key: "late_30", amount: "0.00", share: 0 },
      { key: "late_60", amount: "20.00", share: 0.2 },
      { key: "late_more", amount: "5.00", share: 0.05 },
    ]);
    expect(
      ageParts({ currency: "CHF", not_due: "0", late_30: "0", late_60: "0", late_more: "0" }).map(
        (part) => part.share,
      ),
    ).toEqual([0, 0, 0, 0]);
  });
});
