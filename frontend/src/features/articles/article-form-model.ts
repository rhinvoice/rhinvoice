import type { Path } from "react-hook-form";
import { z } from "zod";

import type { Article, ArticleRequest } from "@/features/articles/api";
import { fields, toApiDecimal } from "@/features/shared/form-schema";
import { taxChoice, taxChoiceOf, taxChoiceToRequest } from "@/features/shared/tax-rate-model";
import { formatDecimalInput } from "@/lib/format";
import type { T } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";

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
    /** The id of one of the company's units (ADR 0046). */
    unit: z.string().min(1, t("validation.required")),
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

/** A new article in ``unit``, the first unit offered. */
export function emptyArticle(unit = ""): ArticleFormValues {
  return {
    number: "",
    name: "",
    description: "",
    group: "",
    unit,
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
    unit: article.unit_id,
    tax: taxChoiceOf(article),
    supply: article.supply,
    price_chf: priceInput(article.prices["CHF"], locale),
    price_eur: priceInput(article.prices["EUR"], locale),
  };
}

/** A copy of the article without its number: saving takes the next one of the sequence. */
export function copiedArticle(article: Article, locale: Locale): ArticleFormValues {
  return { ...articleToForm(article, locale), number: "" };
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
    unit_id: values.unit,
    ...taxChoiceToRequest(values.tax),
    supply: values.supply,
    prices,
  };
}

export function articleFieldFor(apiField: string): Path<ArticleFormValues> | null {
  if (apiField === "prices.CHF") return "price_chf";
  if (apiField === "prices.EUR") return "price_eur";
  if (apiField === "tax_rate_id" || apiField === "pass_through") return "tax";
  if (apiField === "unit_id") return "unit";
  return apiField in emptyArticle() ? (apiField as Path<ArticleFormValues>) : null;
}
