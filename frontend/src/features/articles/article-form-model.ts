import type { Path } from "react-hook-form";
import { z } from "zod";

import type { Article, ArticleRequest } from "@/features/articles/api";
import { fields, toApiDecimal } from "@/features/shared/form-schema";
import { taxChoice, taxChoiceOf, taxChoiceToRequest } from "@/features/shared/tax-rate-model";
import { formatDecimalInput } from "@/lib/format";
import type { T } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";

export type UnitCode = NonNullable<ArticleRequest["unit"]>;

/** Values come from a select with the API's unit list. */
const unitCode = z.custom<UnitCode>(
  (value) => typeof value === "string" && /^[A-Z0-9]{2,3}$/.test(value),
);

export const SUPPLIES = ["service", "goods"] as const;
export const MAX_PRICE = 99_999_999.9999;

export type PriceCurrency = "CHF" | "EUR";

/** The company's currency first: a company in Germany or Austria enters and sees euros first. */
export function priceCurrencies(first: string | undefined): readonly PriceCurrency[] {
  return first === "EUR" ? ["EUR", "CHF"] : ["CHF", "EUR"];
}

export function articleSchema(t: T, locale: Locale) {
  const f = fields(t, locale);
  return z.object({
    number: f.optionalText(30),
    name: f.requiredText(120),
    description: f.optionalText(4000),
    group: f.optionalText(50),
    unit: unitCode,
    /** A rate id, PASS_THROUGH, or "" for the default rate (ADR 0044). */
    tax: taxChoice,
    supply: z.enum(SUPPLIES),
    price_chf: f.decimal({ max: MAX_PRICE, decimals: 4 }),
    price_eur: f.decimal({ max: MAX_PRICE, decimals: 4 }),
  });
}

export type ArticleFormValues = z.infer<ReturnType<typeof articleSchema>>;

export const ARTICLE_FIELD_ORDER: readonly (keyof ArticleFormValues)[] = [
  "name",
  "number",
  "description",
  "group",
  "unit",
  "tax",
  "supply",
  "price_chf",
  "price_eur",
];

export function emptyArticle(): ArticleFormValues {
  return {
    number: "",
    name: "",
    description: "",
    group: "",
    unit: "C62",
    tax: "",
    supply: "service",
    price_chf: "",
    price_eur: "",
  };
}

function priceInput(value: string | undefined, locale: Locale): string {
  return value === undefined ? "" : formatDecimalInput(value, locale);
}

export function articleToForm(article: Article, locale: Locale): ArticleFormValues {
  return {
    number: article.number,
    name: article.name,
    description: article.description,
    group: article.group,
    unit: article.unit,
    tax: taxChoiceOf(article),
    supply: article.supply,
    price_chf: priceInput(article.prices["CHF"], locale),
    price_eur: priceInput(article.prices["EUR"], locale),
  };
}

export function formToRequest(values: ArticleFormValues, locale: Locale): ArticleRequest {
  const prices: ArticleRequest["prices"] = {};
  if (values.price_chf !== "") prices["CHF"] = toApiDecimal(values.price_chf, locale);
  if (values.price_eur !== "") prices["EUR"] = toApiDecimal(values.price_eur, locale);
  return {
    number: values.number,
    name: values.name,
    description: values.description,
    group: values.group,
    unit: values.unit,
    ...taxChoiceToRequest(values.tax),
    supply: values.supply,
    prices,
  };
}

export function articleFieldFor(apiField: string): Path<ArticleFormValues> | null {
  if (apiField === "prices.CHF") return "price_chf";
  if (apiField === "prices.EUR") return "price_eur";
  if (apiField === "tax_rate_id" || apiField === "pass_through") return "tax";
  return apiField in emptyArticle() ? (apiField as Path<ArticleFormValues>) : null;
}
