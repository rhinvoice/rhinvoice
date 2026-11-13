import type { Path } from "react-hook-form";
import { z } from "zod";

import type { RateCategory, TaxRate, TaxRateRequest } from "@/features/tax-rates/api";
import { fields, toApiDecimal } from "@/features/shared/form-schema";
import { percentOn } from "@/features/shared/tax-rate-model";
import { formatDate, formatDecimalInput, formatPercent } from "@/lib/format";
import { parseDecimal } from "@/lib/format/parse-decimal";
import type { T } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";

/** S: taxed above 0 %, Z: zero-rated, E: exempt with a reason (EN 16931, ADR 0044). */
export const RATE_CATEGORIES = ["S", "Z", "E"] as const satisfies readonly RateCategory[];
export const MAX_RATE_NAME = 60;
export const MAX_RATE_TEXT = 300;
export const MAX_RATE_VALUES = 30;
/** Percentages run from 0 to below 100 with two decimal places. */
const MAX_PERCENT = 99.99;

export function rateValueSchema(t: T, locale: Locale) {
  const f = fields(t, locale);
  return z.object({
    valid_from: z
      .string()
      .regex(/^(\d{4}-\d{2}-\d{2})?$/)
      .refine((value) => value !== "", t("validation.required")),
    percent: f.decimal({ max: MAX_PERCENT, decimals: 2, required: true }),
  });
}

export type RateValueFormValues = z.infer<ReturnType<typeof rateValueSchema>>;

/**
 * What is wrong with a percentage for the category (EN 16931): S needs more than 0 %,
 * Z and E need 0 %. Null when it fits or is no number (the field says that).
 */
export function percentProblem(
  category: RateCategory,
  input: string,
  locale: Locale,
  t: T,
): string | null {
  const percent = parseDecimal(input, locale);
  if (percent === null) return null;
  const zero = Number(percent) === 0;
  if (category === "S") return zero ? t("error.rate_standard_needs_percent") : null;
  return zero ? null : t("error.rate_zero_needs_zero");
}

/** The rules the server checks on saving (EN 16931), here as the user types. */
export function taxRateSchema(t: T, locale: Locale) {
  const f = fields(t, locale);
  return z
    .object({
      name: f.requiredText(MAX_RATE_NAME),
      category: z.enum(RATE_CATEGORIES),
      /** Oldest first; each applies from its date until the next one. */
      values: z.array(rateValueSchema(t, locale)).min(1).max(MAX_RATE_VALUES),
      exemption_reason: f.optionalText(MAX_RATE_TEXT),
      notice: f.optionalText(MAX_RATE_TEXT),
    })
    .superRefine((values, context) => {
      values.values.forEach((value, index) => {
        const problem = percentProblem(values.category, value.percent, locale, t);
        if (problem !== null) {
          context.addIssue({
            code: "custom",
            path: ["values", index, "percent"],
            message: problem,
          });
        }
      });
      if (values.category === "E" && values.exemption_reason === "") {
        context.addIssue({
          code: "custom",
          path: ["exemption_reason"],
          message: t("error.rate_exempt_needs_reason"),
        });
      }
    });
}

export type TaxRateFormValues = z.infer<ReturnType<typeof taxRateSchema>>;

/** A new rate: taxable, valid from the start of the year (drafts of the year can take it). */
export function emptyTaxRate(today: string): TaxRateFormValues {
  return {
    name: "",
    category: "S",
    values: [{ valid_from: `${today.slice(0, 4)}-01-01`, percent: "" }],
    exemption_reason: "",
    notice: "",
  };
}

export function taxRateToForm(rate: TaxRate, locale: Locale): TaxRateFormValues {
  return {
    name: rate.name,
    category: rate.category,
    values: rate.values.map((value) => ({
      valid_from: value.valid_from,
      percent: formatDecimalInput(value.percent, locale, 0, 2),
    })),
    exemption_reason: rate.exemption_reason,
    notice: rate.notice,
  };
}

export function formToRequest(values: TaxRateFormValues, locale: Locale): TaxRateRequest {
  return {
    name: values.name,
    category: values.category,
    values: values.values.map((value) => ({
      valid_from: value.valid_from,
      percent: toApiDecimal(value.percent, locale),
    })),
    // Only exempt rates name a reason; it would be printed with the line.
    exemption_reason: values.category === "E" ? values.exemption_reason : "",
    notice: values.notice,
  };
}

/** The value the form shows: the one in force today, else the first that comes. */
export function currentIndex(
  values: readonly { readonly valid_from: string }[],
  today: string,
): number {
  let index = 0;
  values.forEach((value, at) => {
    if (value.valid_from <= today) index = at;
  });
  return index;
}

/** Add a percentage from a date; one on the same date is replaced. Oldest first. */
export function withValue(
  values: readonly RateValueFormValues[],
  added: RateValueFormValues,
): RateValueFormValues[] {
  return [...values.filter((value) => value.valid_from !== added.valid_from), added].sort((a, b) =>
    a.valid_from.localeCompare(b.valid_from),
  );
}

/**
 * What the list says below a rate's name (variant 1A): a change to come or the one in
 * force since its date, the reason of an exempt rate and the notice on documents.
 */
export function rateSubline(rate: TaxRate, today: string, locale: Locale, t: T): string {
  const parts: string[] = [];
  const next = rate.values.find((value) => value.valid_from > today);
  const at = currentIndex(rate.values, today);
  const current = rate.values[at];
  const previous = rate.values[at - 1];
  if (next !== undefined) {
    parts.push(
      t("taxRates.from", {
        date: formatDate(next.valid_from, locale),
        percent: formatPercent(next.percent, locale),
      }),
    );
  } else if (current !== undefined && previous !== undefined) {
    parts.push(
      t("taxRates.since", {
        date: formatDate(current.valid_from, locale),
        percent: formatPercent(previous.percent, locale),
      }),
    );
  }
  if (rate.category === "E")
    parts.push(t("taxRates.reasonShort", { reason: rate.exemption_reason }));
  if (rate.notice !== "") parts.push(rate.notice);
  return parts.join(" · ");
}

/** Today's percentage of a rate, "–" before its first value. */
export function todayPercent(rate: TaxRate, today: string, locale: Locale): string {
  const percent = percentOn(rate, today);
  return percent === null ? "–" : formatPercent(percent, locale);
}

/** A source of a preset: its address as a link and what it names there, e.g. the paragraph. */
export function sourceLink(source: string): { readonly url: string | null; readonly note: string } {
  const url = /^https:\/\/\S+/.exec(source)?.[0];
  return url === undefined
    ? { url: null, note: source }
    : { url, note: source.slice(url.length).trim() };
}

const RATE_FIELDS = ["name", "category", "exemption_reason", "notice"] as const;

/** Map API error fields ("values.1.percent") onto form fields. */
export function taxRateFieldFor(apiField: string): Path<TaxRateFormValues> | null {
  if ((RATE_FIELDS as readonly string[]).includes(apiField)) {
    return apiField as Path<TaxRateFormValues>;
  }
  return /^values\.\d+\.(percent|valid_from)$/.test(apiField)
    ? (apiField as Path<TaxRateFormValues>)
    : null;
}
