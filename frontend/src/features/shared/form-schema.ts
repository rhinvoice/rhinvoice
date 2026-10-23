import { z } from "zod";

import { formatDecimalInput, formatNumber } from "@/lib/format";
import { parseDecimal } from "@/lib/format/parse-decimal";
import type { T } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";
import { expectedIbanLength, ibanProblem, isQrIban, normalizeIban } from "@/lib/validation/iban";
import { vatProblem } from "@/lib/validation/vat-number";

/** Zod building blocks with German/English messages, shared by all forms. */
export function fields(t: T, locale: Locale) {
  const optionalText = (max: number) =>
    z.string().trim().max(max, t("validation.maxLength", { max }));
  const requiredText = (max: number) => optionalText(max).min(1, t("validation.required"));
  return {
    optionalText,
    requiredText,
    email: z
      .string()
      .trim()
      .max(254, t("validation.maxLength", { max: 254 }))
      .refine((value) => value === "" || z.email().safeParse(value).success, t("validation.email")),
    vatNumber: z
      .string()
      .trim()
      .max(40, t("validation.maxLength", { max: 40 }))
      .superRefine((value, context) => {
        const problem = vatProblem(value);
        if (problem !== null)
          context.addIssue({ code: "custom", message: t(`validation.vat.${problem}`) });
      }),
    iban: z
      .string()
      .trim()
      .superRefine((value, context) => {
        const problem = ibanProblem(value);
        if (problem === "length") {
          // A length problem implies a known country, so the expected length exists.
          context.addIssue({
            code: "custom",
            message: t("validation.iban.length", {
              country: normalizeIban(value).slice(0, 2),
              length: String(expectedIbanLength(value)),
            }),
          });
        } else if (problem !== null) {
          context.addIssue({ code: "custom", message: t(`validation.iban.${problem}`) });
        } else if (isQrIban(value)) {
          context.addIssue({ code: "custom", message: t("validation.iban.isQr") });
        }
      }),
    /**
     * Locale-tolerant decimal input ("1’234.50", "1.234,50") within range;
     * ``signed`` also allows negative values down to ``-max``.
     */
    decimal: (options: { max: number; decimals: number; required?: boolean; signed?: boolean }) =>
      z
        .string()
        .trim()
        .superRefine((value, context) => {
          if (value === "") {
            if (options.required === true)
              context.addIssue({ code: "custom", message: t("validation.required") });
            return;
          }
          const parsed = parseDecimal(value, locale);
          if (parsed === null) {
            const example = formatDecimalInput("12.5", locale);
            context.addIssue({ code: "custom", message: t("validation.number", { example }) });
            return;
          }
          const negativeAllowed = options.signed === true;
          if (
            (parsed.startsWith("-") && !negativeAllowed) ||
            Math.abs(Number(parsed)) > options.max
          ) {
            // Name the allowed range: "-12" or "150" in a discount is a number, just not one that fits.
            const max = formatNumber(String(options.max), locale, options.decimals);
            const min = negativeAllowed
              ? formatNumber(String(-options.max), locale, options.decimals)
              : "0";
            context.addIssue({ code: "custom", message: t("validation.range", { min, max }) });
            return;
          }
          const fraction = parsed.split(".")[1] ?? "";
          if (fraction.length > options.decimals) {
            context.addIssue({
              code: "custom",
              message: t("validation.decimals", { max: options.decimals }),
            });
          }
        }),
    days: z
      .string()
      .trim()
      .refine(
        (value) => value === "" || (/^\d{1,3}$/.test(value) && Number(value) <= 365),
        t("validation.days"),
      ),
  };
}

/** Convert a validated decimal input into the API's canonical form ("1234.5"). */
export function toApiDecimal(value: string, locale: Locale): string {
  return parseDecimal(value, locale) ?? "0";
}
