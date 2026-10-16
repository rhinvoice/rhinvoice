import { intlLocale, numberLocale, numericMediumDates, type Locale } from "@/lib/locale";

/**
 * All user visible numbers, amounts and dates go through these functions.
 * Formatter instances are cached because constructing them is expensive.
 */
const cache = new Map<string, Intl.NumberFormat | Intl.DateTimeFormat | Intl.RelativeTimeFormat>();

function cached<T extends Intl.NumberFormat | Intl.DateTimeFormat | Intl.RelativeTimeFormat>(
  key: string,
  create: () => T,
): T {
  const existing = cache.get(key);
  if (existing !== undefined) {
    return existing as T;
  }
  const created = create();
  cache.set(key, created);
  return created;
}

/**
 * Amounts are passed as decimal strings from the API to avoid float rounding.
 * Totals use two decimals; unit prices may show up to four (``maximumFractionDigits``).
 */
export function formatMoney(
  amount: string,
  currency: string,
  locale: Locale,
  maximumFractionDigits = 2,
): string {
  const formatter = cached(
    `money:${locale}:${currency}:${maximumFractionDigits}`,
    () =>
      new Intl.NumberFormat(numberLocale(locale), {
        style: "currency",
        currency,
        currencyDisplay: "code",
        minimumFractionDigits: 2,
        maximumFractionDigits,
      }),
  );
  return formatter.format(amount as Intl.StringNumericLiteral);
}

export function formatNumber(value: string, locale: Locale, maximumFractionDigits = 3): string {
  const formatter = cached(
    `number:${locale}:${maximumFractionDigits}`,
    () => new Intl.NumberFormat(numberLocale(locale), { maximumFractionDigits }),
  );
  return formatter.format(value as Intl.StringNumericLiteral);
}

/**
 * Decimal for editing in an input: locale decimal separator, no grouping,
 * e.g. "150.00" (de-CH) or "150,00" (de-DE).
 */
export function formatDecimalInput(
  value: string,
  locale: Locale,
  minimumFractionDigits = 2,
  maximumFractionDigits = 4,
): string {
  const formatter = cached(
    `input:${locale}:${minimumFractionDigits}:${maximumFractionDigits}`,
    () =>
      new Intl.NumberFormat(numberLocale(locale), {
        useGrouping: false,
        minimumFractionDigits,
        maximumFractionDigits,
      }),
  );
  return formatter.format(value as Intl.StringNumericLiteral);
}

/** Format a percentage given in percent points, e.g. "8.1" → "8.1%" / "8,1 %". */
export function formatPercent(rate: string, locale: Locale): string {
  const formatter = cached(
    `percent:${locale}`,
    () =>
      new Intl.NumberFormat(numberLocale(locale), { style: "percent", maximumFractionDigits: 2 }),
  );
  return formatter.format(Number(rate) / 100);
}

/** A change as signed percent, e.g. "+12 %" / "−7 %" / "0 %"; ``fraction`` 0.12 is 12 %. */
export function formatChange(fraction: number, locale: Locale): string {
  const formatter = cached(
    `change:${locale}`,
    () =>
      new Intl.NumberFormat(numberLocale(locale), {
        style: "percent",
        maximumFractionDigits: 0,
        signDisplay: "exceptZero",
      }),
  );
  // Rounded first, so that a change of -0.3 % reads "0 %", not "-0 %".
  return formatter.format(Math.round(fraction * 100) / 100 || 0);
}

export type DateStyle = "medium" | "long";

const NUMERIC_DATE = { day: "2-digit", month: "2-digit", year: "numeric" } as const;

/** Medium dates are numeric in every Swiss locale (05.01.2026), long dates spell the month. */
function dateOptions(locale: Locale, style: DateStyle): Intl.DateTimeFormatOptions {
  return style === "medium" && numericMediumDates(locale) ? NUMERIC_DATE : { dateStyle: style };
}

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})/;

/**
 * Format an ISO date ("2026-01-05") without timezone shifts.
 * Input that is not an ISO date is returned unchanged.
 */
export function formatDate(isoDate: string, locale: Locale, style: DateStyle = "medium"): string {
  const match = ISO_DATE.exec(isoDate);
  if (match === null) {
    return isoDate;
  }
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  const formatter = cached(
    `date:${locale}:${style}`,
    () =>
      new Intl.DateTimeFormat(intlLocale(locale), {
        ...dateOptions(locale, style),
        timeZone: "UTC",
      }),
  );
  return formatter.format(date);
}

export function formatDateTime(isoDateTime: string, locale: Locale, timeZone?: string): string {
  const formatter = cached(
    `datetime:${locale}:${timeZone ?? "local"}`,
    () =>
      new Intl.DateTimeFormat(intlLocale(locale), {
        ...(numericMediumDates(locale)
          ? { ...NUMERIC_DATE, hour: "2-digit", minute: "2-digit" }
          : { dateStyle: "medium", timeStyle: "short" }),
        ...(timeZone === undefined ? {} : { timeZone }),
      }),
  );
  return formatter.format(new Date(isoDateTime));
}

const RELATIVE_UNITS: readonly [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
];

/** "vor 2 Sekunden" / "2 seconds ago", relative to ``now``. */
export function formatRelative(from: Date, now: Date, locale: Locale): string {
  const seconds = Math.round((from.getTime() - now.getTime()) / 1000);
  const formatter = cached(
    `relative:${locale}`,
    () => new Intl.RelativeTimeFormat(intlLocale(locale), { numeric: "auto" }),
  );
  for (const [unit, size] of RELATIVE_UNITS) {
    if (Math.abs(seconds) >= size) {
      return formatter.format(Math.trunc(seconds / size), unit);
    }
  }
  return formatter.format(seconds, "second");
}

/** Short month of an ISO date, e.g. "Jan. 26" (de-AT: "Jän. 26"). */
export function formatMonth(isoDate: string, locale: Locale): string {
  const match = ISO_DATE.exec(isoDate);
  if (match === null) {
    return isoDate;
  }
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, 1));
  const formatter = cached(
    `month:${locale}`,
    () =>
      new Intl.DateTimeFormat(intlLocale(locale), {
        month: "short",
        year: "2-digit",
        timeZone: "UTC",
      }),
  );
  return formatter.format(date);
}

const BYTE_UNITS = [
  ["byte", 1],
  ["kilobyte", 1e3],
  ["megabyte", 1e6],
  ["gigabyte", 1e9],
] as const;

/** Sizes in decimal units, as storage providers bill them: "48 kB", "1,2 MB". */
export function formatBytes(bytes: number, locale: Locale): string {
  // The largest unit not above the size, or the next one when rounding gives 1000
  // ("999,95 kB" would show as "1000 kB", it becomes "1 MB").
  let [unit, size]: readonly [string, number] = BYTE_UNITS[0];
  for (const candidate of BYTE_UNITS) {
    if (bytes >= candidate[1] || Math.round((bytes / size) * 10) / 10 >= 1000) {
      [unit, size] = candidate;
    }
  }
  const formatter = cached(
    `bytes:${locale}:${unit}`,
    () =>
      new Intl.NumberFormat(intlLocale(locale), {
        style: "unit",
        unit,
        unitDisplay: "short",
        maximumFractionDigits: 1,
      }),
  );
  return formatter.format(bytes / size);
}
