import type { Dashboard } from "@/features/dashboard/api";
import { monthWindow } from "@/lib/dates";

type Revenue = Dashboard["revenue"];
type AgingRow = Dashboard["aging"][number];

/**
 * The currencies of the overview: those with figures first (the API orders
 * them), then any that only appear in revenue, quotes or open invoices.
 */
/** The company's currency first, then those with figures, then the others once. */
export function dashboardCurrencies(data: Dashboard): string[] {
  const seen = new Set<string>([
    ...(data.currency === null ? [] : [data.currency]),
    ...data.figures.map((figure) => figure.currency),
  ]);
  const others = [
    ...data.revenue.map((item) => item.currency),
    ...data.quotes.map((item) => item.currency),
    ...data.aging.map((item) => item.currency),
  ]
    .filter((currency) => !seen.has(currency))
    .sort();
  return [...seen, ...new Set(others)];
}

function revenueOf(revenue: Revenue, currency: string, month: string): number {
  const item = revenue.find((entry) => entry.currency === currency && entry.month === month);
  return item === undefined ? 0 : Number(item.net);
}

export interface YearComparison {
  /** First days of January to December of this year. */
  readonly months: readonly string[];
  /** Net revenue per month of this year; null for months still to come. */
  readonly current: readonly (number | null)[];
  /** Net revenue of the same months last year. */
  readonly previous: readonly number[];
}

/** This year's revenue month by month against the same months of last year (for drawing). */
export function yearComparison(revenue: Revenue, currency: string, today: string): YearComparison {
  const year = Number(today.slice(0, 4));
  const thisMonth = Number(today.slice(5, 7));
  const months = Array.from(
    { length: 12 },
    (_, index) => `${String(year)}-${String(index + 1).padStart(2, "0")}-01`,
  );
  return {
    months,
    current: months.map((month, index) =>
      index < thisMonth ? revenueOf(revenue, currency, month) : null,
    ),
    previous: months.map((month) =>
      revenueOf(revenue, currency, `${String(year - 1)}${month.slice(4)}`),
    ),
  };
}

/**
 * Change of this year's revenue to date against last year up to the same day,
 * as a fraction (0.12 = +12 %); null without revenue last year.
 */
export function yearChange(current: string, previous: string): number | null {
  const before = Number(previous);
  return before > 0 ? (Number(current) - before) / before : null;
}

/** Net revenue of the last ``count`` months up to today's, oldest first (for a trend line). */
export function recentMonths(
  revenue: Revenue,
  currency: string,
  today: string,
  count = 12,
): number[] {
  return monthWindow(today, count).map((month) => revenueOf(revenue, currency, month));
}

/** Share of accepted quotes among the decided ones; null when none was decided. */
export function acceptanceRate(accepted: number, decided: number): number | null {
  return decided > 0 ? accepted / decided : null;
}

export type AgeKey = "not_due" | "late_30" | "late_60" | "late_more";

export const AGE_KEYS: readonly AgeKey[] = ["not_due", "late_30", "late_60", "late_more"];

export interface AgePart {
  readonly key: AgeKey;
  readonly amount: string;
  /** Share of all open invoices, 0 to 1 (for drawing). */
  readonly share: number;
}

/** The open invoices of one currency split by age, with their shares. */
export function ageParts(aging: AgingRow): AgePart[] {
  const total = sum(AGE_KEYS.map((key) => Number(aging[key])));
  return AGE_KEYS.map((key) => ({
    key,
    amount: aging[key],
    share: total > 0 ? Number(aging[key]) / total : 0,
  }));
}

function sum(values: readonly number[]): number {
  return values.reduce((total, value) => total + value, 0);
}
