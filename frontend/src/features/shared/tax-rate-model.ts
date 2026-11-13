import { z } from "zod";

import type { TaxRate } from "@/features/shared/tax-rates-api";
import { formatPercent } from "@/lib/format";
import type { T } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";

/**
 * The tax choice of a line or an article: a rate id, PASS_THROUGH, or "" for the default
 * rate the server picks (ADR 0044). Pass-through items take no rate (ADR 0039).
 */
export const PASS_THROUGH = "pass_through";

/** A tax choice in a form: a rate id, PASS_THROUGH or "" for the default rate. */
export const taxChoice = z.union([z.literal(""), z.literal(PASS_THROUGH), z.guid()]);

/** The key of the preset that lines without a rate take, as the server picks it. */
const STANDARD_PRESET = "standard";

/** Percentages by rate id, as the document preview names them for its date of supply. */
export type Percents = Readonly<Record<string, string>>;

/** The percentage of a rate on a day (ISO date); null before its first value. */
export function percentOn(rate: Pick<TaxRate, "values">, day: string): string | null {
  // The values are ordered oldest first; each applies until the next one.
  let percent: string | null = null;
  for (const value of rate.values) {
    if (value.valid_from <= day) percent = value.percent;
  }
  return percent;
}

/** The percentage of each rate on a day; rates not valid yet are left out, as in the preview. */
export function percentsOn(rates: readonly TaxRate[], day: string): Percents {
  const percents: Record<string, string> = {};
  for (const rate of rates) {
    const percent = percentOn(rate, day);
    if (percent !== null) percents[rate.id] = percent;
  }
  return percents;
}

/** The rate of positions that name none: the standard preset, else the first taxable rate. */
export function defaultRateId(rates: readonly TaxRate[]): string | null {
  const taxed = rates.filter((rate) => !rate.hidden && rate.category === "S");
  return (taxed.find((rate) => rate.preset === STANDARD_PRESET) ?? taxed[0])?.id ?? null;
}

/** The choice that ``choice`` stands for: "" is the default rate (null without one). */
export function resolvedChoice(rates: readonly TaxRate[], choice: string): string | null {
  return choice === "" ? defaultRateId(rates) : choice;
}

/** The choice of a stored line or article; pass-through items name no rate. */
export function taxChoiceOf(stored: {
  readonly tax_category: string;
  readonly tax_rate_id: string | null;
}): string {
  return stored.tax_category === PASS_THROUGH ? PASS_THROUGH : (stored.tax_rate_id ?? "");
}

/** What the API takes for a choice. */
export function taxChoiceToRequest(choice: string): {
  readonly tax_rate_id: string | null;
  readonly pass_through: boolean;
} {
  const passThrough = choice === PASS_THROUGH;
  return { tax_rate_id: passThrough || choice === "" ? null : choice, pass_through: passThrough };
}

export interface TaxOption {
  readonly value: string;
  readonly label: string;
}

/** The choices of a line or an article, grouped into taxable and without tax (variant 3B). */
export interface TaxOptions {
  readonly taxed: readonly TaxOption[];
  readonly untaxed: readonly TaxOption[];
}

/**
 * The rates to choose from, each "Name – 8.1 %": hidden ones only where already chosen
 * (marked as hidden), and the pass-through item last. ``percents`` gives the percentage on
 * the date of supply; a rate without one (not valid yet) shows its name only.
 */
export function taxOptions(
  rates: readonly TaxRate[],
  choice: string,
  percents: Percents,
  passThroughLabel: string,
  locale: Locale,
  t: T,
): TaxOptions {
  const chosen = resolvedChoice(rates, choice);
  const option = (rate: TaxRate): TaxOption => {
    const name = rate.hidden ? t("taxRates.nameHidden", { name: rate.name }) : rate.name;
    const percent = percents[rate.id];
    return {
      value: rate.id,
      label: percent === undefined ? name : `${name} – ${formatPercent(percent, locale)}`,
    };
  };
  const offered = rates.filter((rate) => !rate.hidden || rate.id === chosen);
  return {
    taxed: offered.filter((rate) => rate.category === "S").map(option),
    untaxed: [
      ...offered.filter((rate) => rate.category !== "S").map(option),
      { value: PASS_THROUGH, label: passThroughLabel },
    ],
  };
}

/**
 * The rate of a line in short: "8.1 %", or "Normalsatz (19 %)" where another offered rate
 * has the same percentage on that day; its name without a percentage. Null for pass-through
 * items and unknown rates.
 */
export function shortRate(
  rates: readonly TaxRate[],
  choice: string,
  percents: Percents,
  locale: Locale,
): string | null {
  const chosen = resolvedChoice(rates, choice);
  const rate = rates.find((candidate) => candidate.id === chosen);
  if (rate === undefined) return null;
  const percent = percents[rate.id];
  if (percent === undefined) return rate.name;
  const shared = rates.some(
    (other) =>
      other.id !== rate.id &&
      !other.hidden &&
      percents[other.id] !== undefined &&
      Number(percents[other.id]) === Number(percent),
  );
  const formatted = formatPercent(percent, locale);
  return shared ? `${rate.name} (${formatted})` : formatted;
}
