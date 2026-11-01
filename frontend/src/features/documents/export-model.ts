import type { Locale } from "@/lib/locale";

/** The list's formats; with PDFs everything comes as one ZIP. */
export const EXPORT_FORMATS = ["xlsx", "csv", "pdf"] as const;
export type ExportFormat = (typeof EXPORT_FORMATS)[number];

export const PERIOD_KINDS = ["month", "quarter", "year", "custom"] as const;
export type PeriodKind = (typeof PERIOD_KINDS)[number];

export const QUARTERS = [1, 2, 3, 4] as const;
export const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] as const;

/** The longest period the server exports (ten years, the first day plus less than ten years). */
export const MAX_PERIOD_YEARS = 10;

export interface ExportChoice {
  readonly kind: PeriodKind;
  readonly year: number;
  readonly month: number;
  readonly quarter: number;
  /** First and last day of a free period (ISO dates, "" while empty). */
  readonly from: string;
  readonly to: string;
  readonly format: ExportFormat;
  readonly withPdfs: boolean;
}

export interface Period {
  readonly start: string;
  readonly end: string;
}

export type PeriodProblem = "missing" | "reversed" | "tooLong";

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

function lastDay(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

function monthPeriod(year: number, first: number, last: number): Period {
  return {
    start: `${String(year)}-${pad(first)}-01`,
    end: `${String(year)}-${pad(last)}-${pad(lastDay(year, last))}`,
  };
}

/** The dialog starts with the previous full month, the usual request of the bookkeeping. */
export function defaultChoice(today: string): ExportChoice {
  const year = Number(today.slice(0, 4));
  const month = Number(today.slice(5, 7));
  const previousYear = month === 1 ? year - 1 : year;
  const previousMonth = month === 1 ? 12 : month - 1;
  const start = `${String(previousYear)}-${pad(previousMonth)}-01`;
  const end = monthPeriod(previousYear, previousMonth, previousMonth).end;
  return {
    kind: "month",
    year: previousYear,
    month: previousMonth,
    quarter: Math.ceil(previousMonth / 3),
    from: start,
    to: end,
    format: "xlsx",
    withPdfs: false,
  };
}

/** The years to choose from: those with documents, the current and the chosen one, newest first. */
export function yearOptions(today: string, known: readonly number[], chosen: number): number[] {
  const years = new Set([...known, Number(today.slice(0, 4)), chosen]);
  return [...years].sort((first, second) => second - first);
}

/** The ISO date ten years after a day: the first day a period may no longer reach. */
function tenYearsLater(start: string): string {
  const year = Number(start.slice(0, 4)) + MAX_PERIOD_YEARS;
  const rest = start.slice(4);
  // 29 February becomes the 28th, as on the server: ten years after a leap year is none.
  return `${String(year)}${rest === "-02-29" ? "-02-28" : rest}`;
}

/** What is wrong with a free period, or null; the other kinds are always valid. */
export function periodProblem(choice: ExportChoice): PeriodProblem | null {
  if (choice.kind !== "custom") return null;
  const { from, to } = choice;
  if (!ISO_DATE.test(from) || !ISO_DATE.test(to)) return "missing";
  if (to < from) return "reversed";
  if (to >= tenYearsLater(from)) return "tooLong";
  return null;
}

/** The first and last day of the chosen period, or null while a free period is invalid. */
export function periodOf(choice: ExportChoice): Period | null {
  switch (choice.kind) {
    case "month":
      return monthPeriod(choice.year, choice.month, choice.month);
    case "quarter":
      return monthPeriod(choice.year, choice.quarter * 3 - 2, choice.quarter * 3);
    case "year":
      return monthPeriod(choice.year, 1, 12);
    case "custom":
      return periodProblem(choice) === null ? { start: choice.from, end: choice.to } : null;
  }
}

/** The language of the list's column headers: the one the program is used in. */
export function exportLanguage(locale: Locale): "de" | "en" | "fr" | "it" {
  if (locale === "en") return "en";
  if (locale === "fr-CH") return "fr";
  if (locale === "it-CH") return "it";
  return "de";
}

export function exportUrl(choice: ExportChoice, period: Period, locale: Locale): string {
  const params = new URLSearchParams({
    start: period.start,
    end: period.end,
    format: choice.format,
    pdfs: String(choice.withPdfs),
    language: exportLanguage(locale),
  });
  return `/api/exports/invoices?${params.toString()}`;
}

/** The name to save under when the server names none (it always does). */
export function fallbackName(choice: ExportChoice, period: Period): string {
  const extension = choice.withPdfs ? "zip" : choice.format;
  return `export ${period.start} ${period.end}.${extension}`;
}
