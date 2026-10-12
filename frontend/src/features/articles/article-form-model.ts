import type { Path } from "react-hook-form";
import { z } from "zod";

import type { Article, ArticleRequest } from "@/features/articles/api";
import { fields, toApiDecimal } from "@/features/shared/form-schema";
import { formatDecimalInput } from "@/lib/format";
import type { T } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";

export type UnitCode = NonNullable<ArticleRequest["unit"]>;

/** Values come from a select with the API's unit list. */
const unitCode = z.custom<UnitCode>(
  (value) => typeof value === "string" && /^[A-Z0-9]{2,3}$/.test(value),
);

export const TAX_CATEGORIES = ["standard", "reduced", "special", "zero", "exempt"] as const;
export const SUPPLIES = ["service", "goods"] as const;
export const MAX_PRICE = 99_999_999.9999;

export function articleSchema(t: T, locale: Locale) {
  const f = fields(t, locale);
  return z.object({
    number: f.optionalText(30),
    name: f.requiredText(120),
    description: f.optionalText(4000),
    group: f.optionalText(50),
    unit: unitCode,
    tax_category: z.enum(TAX_CATEGORIES),
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
  "tax_category",
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
    tax_category: "standard",
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
    tax_category: article.tax_category,
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
    tax_category: values.tax_category,
    supply: values.supply,
    prices,
  };
}

export function articleFieldFor(apiField: string): Path<ArticleFormValues> | null {
  if (apiField === "prices.CHF") return "price_chf";
  if (apiField === "prices.EUR") return "price_eur";
  return apiField in emptyArticle() ? (apiField as Path<ArticleFormValues>) : null;
}
