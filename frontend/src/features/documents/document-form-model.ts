import type { FieldErrors, Path } from "react-hook-form";
import { z } from "zod";

import type { ErrorSummaryItem } from "@/components/ui/error-summary";
import type {
  ArticleOption,
  CustomerOption,
  DocumentDetail,
  DraftRequest,
  TaxTreatment,
} from "@/features/documents/api";
import type { Company } from "@/features/shared/company-api";
import { DOCUMENT_LANGUAGES } from "@/features/shared/document-languages";
import { fields, toApiDecimal } from "@/features/shared/form-schema";
import { formatDecimalInput } from "@/lib/format";
import type { T } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";

export type LineRequest = NonNullable<DraftRequest["lines"]>[number];
export type UnitCode = NonNullable<LineRequest["unit"]>;
export type Currency = "CHF" | "EUR";

export const TAX_CATEGORIES = ["standard", "reduced", "special", "zero", "exempt"] as const;
export const SUPPLIES = ["service", "goods"] as const;
/** Treatments that can be chosen for a document; goods get theirs from it. */
export const TREATMENTS = [
  "domestic",
  "reverse_charge",
  "export",
  "small_business",
  "exempt",
] as const satisfies readonly TaxTreatment[];
export const MAX_LINES = 500;

function isChoosable(treatment: TaxTreatment): treatment is (typeof TREATMENTS)[number] {
  return (TREATMENTS as readonly string[]).includes(treatment);
}
export const MAX_PRICE = 99_999_999.9999;
export const MAX_QUANTITY = 999_999_999.9999;
export const MAX_DISCOUNT_AMOUNT = 9_999_999_999.99;

/** Values come from a select with the API's unit list. */
const unitCode = z.custom<UnitCode | "">(
  (value) => typeof value === "string" && /^([A-Z0-9]{2,3})?$/.test(value),
);
const isoDate = z.string().regex(/^(\d{4}-\d{2}-\d{2})?$/);

export function documentSchema(t: T, locale: Locale) {
  const f = fields(t, locale);
  const line = z
    .object({
      key: z.string(),
      kind: z.enum(["item", "text"]),
      description: f.optionalText(500),
      details: f.optionalText(4000),
      quantity: f.decimal({ max: MAX_QUANTITY, decimals: 4, signed: true }),
      unit: unitCode,
      unit_price: f.decimal({ max: MAX_PRICE, decimals: 4 }),
      discount_percent: f.decimal({ max: 100, decimals: 2 }),
      tax_category: z.enum(TAX_CATEGORIES),
      supply: z.enum(SUPPLIES),
      article_id: z.string().nullable(),
    })
    .superRefine((value, context) => {
      if (value.description === "") {
        context.addIssue({
          code: "custom",
          path: ["description"],
          message: t("validation.required"),
        });
      }
      if (value.kind === "item" && value.quantity === "") {
        context.addIssue({ code: "custom", path: ["quantity"], message: t("validation.required") });
      }
    });
  return z
    .object({
      customer_id: z.string(),
      currency: z.enum(["CHF", "EUR"]),
      language: z.enum(DOCUMENT_LANGUAGES),
      price_mode: z.enum(["net", "gross"]),
      issue_date: isoDate,
      due_date: isoDate,
      service_from: isoDate,
      service_to: isoDate,
      subject: f.optionalText(200),
      reference: f.optionalText(100),
      intro_text: f.optionalText(4000),
      payment_text: f.optionalText(4000),
      closing_text: f.optionalText(4000),
      discount_kind: z.enum(["percent", "amount"]),
      discount_value: f.decimal({ max: MAX_DISCOUNT_AMOUNT, decimals: 2 }),
      treatment: z.enum(["", ...TREATMENTS]),
      override_reason: f.optionalText(200),
      lines: z.array(line).max(MAX_LINES, t("documents.tooManyLines", { max: MAX_LINES })),
    })
    .superRefine((values, context) => {
      const issue = (path: keyof DocumentFormValues, message: string) => {
        context.addIssue({ code: "custom", path: [path], message });
      };
      if (values.customer_id === "") issue("customer_id", t("documents.customerRequired"));
      if (values.discount_kind === "percent" && values.discount_value !== "") {
        const percent = Number(toApiDecimal(values.discount_value, locale));
        if (percent > 100) issue("discount_value", t("validation.percent"));
      }
      if (values.treatment !== "" && values.override_reason === "") {
        issue("override_reason", t("documents.overrideReasonRequired"));
      }
      if (values.issue_date !== "" && values.due_date !== "" && values.due_date < values.issue_date)
        issue("due_date", t("documents.dueBeforeIssue"));
      if (
        values.service_from !== "" &&
        values.service_to !== "" &&
        values.service_to < values.service_from
      )
        issue("service_to", t("documents.serviceEndsBeforeStart"));
    });
}

export type DocumentFormValues = z.infer<ReturnType<typeof documentSchema>>;
export type LineFormValues = DocumentFormValues["lines"][number];

let lineCounter = 0;

/**
 * Stable keys for React lists; line ids are reassigned by the server on every
 * save. (Not crypto.randomUUID: it is missing on plain HTTP outside localhost,
 * which is common for self-hosted installations in a local network.)
 */
export function newLineKey(): string {
  lineCounter += 1;
  return `new-${String(lineCounter)}`;
}

export function emptyLine(kind: "item" | "text" = "item"): LineFormValues {
  return {
    key: newLineKey(),
    kind,
    description: "",
    details: "",
    quantity: kind === "item" ? "1" : "",
    unit: kind === "item" ? "C62" : "",
    unit_price: "",
    discount_percent: "",
    tax_category: "standard",
    supply: "service",
    article_id: null,
  };
}

/** Whether a line is still exactly as added: nothing typed, nothing picked. */
export function isBlankLine(line: LineFormValues): boolean {
  return (
    JSON.stringify({ ...line, key: "" }) === JSON.stringify({ ...emptyLine(line.kind), key: "" })
  );
}

export function emptyDocument(company: Company): DocumentFormValues {
  return {
    customer_id: "",
    currency: company.default_currency,
    language: company.default_language,
    price_mode: "net",
    issue_date: "",
    due_date: "",
    service_from: "",
    service_to: "",
    subject: "",
    reference: "",
    intro_text: "",
    payment_text: "",
    closing_text: "",
    discount_kind: "percent",
    discount_value: "",
    treatment: "",
    override_reason: "",
    lines: [emptyLine()],
  };
}

/** Defaults that follow the chosen customer (only for new documents). */
export function customerDefaults(
  customer: CustomerOption,
  company: Company,
  locale: Locale,
): Pick<DocumentFormValues, "customer_id" | "currency" | "language" | "discount_value"> {
  const discount = customer.default_discount;
  return {
    customer_id: customer.id,
    currency: customer.default_currency ?? company.default_currency,
    language: customer.default_language ?? company.default_language,
    discount_value: Number(discount) === 0 ? "" : formatDecimalInput(discount, locale, 0, 2),
  };
}

/** Fill a line from an article; the price follows the document currency. */
export function lineFromArticle(
  line: LineFormValues,
  article: ArticleOption,
  currency: Currency,
  locale: Locale,
): LineFormValues {
  const price = article.prices[currency];
  return {
    ...line,
    kind: "item",
    description: article.name,
    details: article.description,
    unit: article.unit,
    unit_price: price === undefined ? line.unit_price : formatDecimalInput(price, locale),
    tax_category: article.tax_category,
    supply: article.supply,
    article_id: article.id,
  };
}

/** Whether any position (not text line) supplies goods or services. */
export function hasSupply(
  lines: readonly Pick<LineFormValues, "kind" | "supply">[],
  supply: LineFormValues["supply"],
): boolean {
  return lines.some((line) => line.kind === "item" && line.supply === supply);
}

type Rates = Partial<Record<(typeof TAX_CATEGORIES)[number], string>>;

/** The treatment of a line of its own (goods exported, delivered in the EU), or null. */
export function ownTreatment(
  supply: LineFormValues["supply"],
  goodsTreatment: TaxTreatment | null | undefined,
): TaxTreatment | null {
  return supply === "goods" && goodsTreatment !== null && goodsTreatment !== undefined
    ? goodsTreatment
    : null;
}

/** Rates offered for a line: goods exported or delivered in the EU carry no VAT. */
export function lineRates(rates: Rates | undefined, own: TaxTreatment | null): Rates | undefined {
  if (own === null || own === "domestic" || rates === undefined) return rates;
  return Object.fromEntries(Object.keys(rates).map((category) => [category, "0"]));
}

/**
 * What the missing VAT number of an EU business changes: reverse charge for services,
 * an intra-Community supply for goods from DE/AT; nothing for goods from CH/LI (exports).
 */
export function customerVatHint(
  lines: readonly Pick<LineFormValues, "kind" | "supply">[],
  vatSystem: "eu" | "swiss",
  treatment: TaxTreatment,
  goodsTreatment: TaxTreatment | null | undefined,
): { readonly withNumber: TaxTreatment; readonly without: TaxTreatment } | null {
  if (hasSupply(lines, "service") || !hasSupply(lines, "goods")) {
    return { withNumber: "reverse_charge", without: treatment };
  }
  // Goods leave the Swiss VAT area as exports: the VAT number changes nothing.
  if (vatSystem === "swiss") return null;
  return { withNumber: "intra_community", without: goodsTreatment ?? treatment };
}

/** What to keep for goods that leave the country tax free; null when nothing. */
export function goodsHintKey(
  goodsTreatment: TaxTreatment | null | undefined,
  lines: readonly Pick<LineFormValues, "kind" | "supply">[],
): "documents.intraCommunityHint" | "documents.goodsExportHint" | null {
  if (!hasSupply(lines, "goods")) return null;
  if (goodsTreatment === "intra_community") return "documents.intraCommunityHint";
  if (goodsTreatment === "goods_export") return "documents.goodsExportHint";
  return null;
}

function decimalInput(value: string, locale: Locale, minimumFractionDigits = 0): string {
  return Number(value) === 0 ? "" : formatDecimalInput(value, locale, minimumFractionDigits);
}

export function documentToForm(document: DocumentDetail, locale: Locale): DocumentFormValues {
  return {
    customer_id: document.customer_id,
    currency: document.currency,
    language: document.language,
    price_mode: document.price_mode,
    issue_date: document.issue_date ?? "",
    due_date: document.due_date ?? "",
    service_from: document.service_from ?? "",
    service_to: document.service_to ?? "",
    subject: document.subject,
    reference: document.reference,
    intro_text: document.intro_text,
    payment_text: document.payment_text,
    closing_text: document.closing_text,
    discount_kind: document.discount_kind,
    discount_value: decimalInput(document.discount_value, locale),
    treatment:
      document.treatment_overridden && isChoosable(document.treatment) ? document.treatment : "",
    override_reason: "",
    lines: document.lines.map((line) => lineToForm(line, line.id, locale)),
  };
}

/** What a stored line (of a document or a plan) says, as the form edits it. */
export type StoredLine = Omit<DocumentDetail["lines"][number], "id" | "tax_rate" | "amount">;

export function lineToForm(line: StoredLine, key: string, locale: Locale): LineFormValues {
  return {
    key,
    kind: line.kind,
    description: line.description,
    details: line.details,
    quantity: line.kind === "item" ? formatDecimalInput(line.quantity, locale, 0) : "",
    // The API returns stored unit codes, which always come from the unit list.
    unit: (line.unit ?? "") as UnitCode | "",
    unit_price: line.kind === "item" ? decimalInput(line.unit_price, locale, 2) : "",
    discount_percent: decimalInput(line.discount_percent, locale),
    tax_category: line.tax_category,
    supply: line.supply,
    article_id: line.article_id,
  };
}

function apiDecimal(value: string, locale: Locale): string {
  return value === "" ? "0" : toApiDecimal(value, locale);
}

function lineToRequest(line: LineFormValues, locale: Locale): LineRequest {
  if (line.kind === "text") {
    // Text lines have no amount; the server ignores the numeric defaults.
    return {
      kind: "text",
      description: line.description,
      details: line.details,
      quantity: "1",
      unit: null,
      unit_price: "0",
      discount_percent: "0",
      tax_category: "standard",
      supply: "service",
      article_id: null,
    };
  }
  return {
    kind: "item",
    description: line.description,
    details: line.details,
    quantity: apiDecimal(line.quantity, locale),
    unit: line.unit === "" ? null : line.unit,
    unit_price: apiDecimal(line.unit_price, locale),
    discount_percent: apiDecimal(line.discount_percent, locale),
    tax_category: line.tax_category,
    supply: line.supply,
    article_id: line.article_id,
  };
}

const optionalDate = (value: string): string | null => (value === "" ? null : value);

export function formToDraft(values: DocumentFormValues, locale: Locale): DraftRequest {
  return {
    customer_id: values.customer_id,
    currency: values.currency,
    language: values.language,
    price_mode: values.price_mode,
    issue_date: optionalDate(values.issue_date),
    due_date: optionalDate(values.due_date),
    service_from: optionalDate(values.service_from),
    service_to: optionalDate(values.service_to),
    subject: values.subject,
    reference: values.reference,
    intro_text: values.intro_text,
    payment_text: values.payment_text,
    closing_text: values.closing_text,
    discount_kind: values.discount_kind,
    discount_value: apiDecimal(values.discount_value, locale),
    treatment_override: values.treatment === "" ? null : values.treatment,
    override_reason: values.treatment === "" ? "" : values.override_reason,
    lines: values.lines.map((line) => lineToRequest(line, locale)),
  };
}

const TOP_LEVEL_FIELDS = [
  "customer_id",
  "subject",
  "reference",
  "issue_date",
  "due_date",
  "service_from",
  "service_to",
  "currency",
  "language",
  "lines",
  "price_mode",
  "discount_value",
  "treatment",
  "override_reason",
  "intro_text",
  "payment_text",
  "closing_text",
] as const satisfies readonly (keyof DocumentFormValues)[];

const LINE_FIELDS = [
  "description",
  "details",
  "quantity",
  "unit",
  "unit_price",
  "discount_percent",
  "tax_category",
  "supply",
] as const satisfies readonly (keyof LineFormValues)[];

/** Map API error fields ("lines.2.quantity", "discount") onto form fields. */
export function documentFieldFor(apiField: string): Path<DocumentFormValues> | null {
  if (apiField === "discount") return "discount_value";
  if (apiField === "treatment_override") return "treatment";
  if ((TOP_LEVEL_FIELDS as readonly string[]).includes(apiField)) {
    return apiField as Path<DocumentFormValues>;
  }
  const lineField = /^lines\.\d+\.(\w+)$/.exec(apiField)?.[1];
  if (lineField !== undefined && (LINE_FIELDS as readonly string[]).includes(lineField)) {
    return apiField as Path<DocumentFormValues>;
  }
  return null;
}

/** Id of the input of a form field; also the target of error summary links. */
export function fieldId(path: string): string {
  return path.replaceAll(".", "-");
}

/** Error summary items in visual order, including errors inside lines. */
export function documentSummaryItems(
  errors: FieldErrors<DocumentFormValues>,
  t: T,
): ErrorSummaryItem[] {
  const items: ErrorSummaryItem[] = [];
  for (const name of TOP_LEVEL_FIELDS) {
    if (name === "lines") {
      const lines = errors.lines;
      // An array error lives in "root" (validation) or directly on the field (server).
      const linesMessage = lines?.root?.message ?? lines?.message;
      if (typeof linesMessage === "string") {
        items.push({ fieldId: fieldId("lines"), message: linesMessage });
      }
      const entries = Array.isArray(lines) ? (lines as FieldErrors<LineFormValues>[]) : [];
      entries.forEach((lineErrors, index) => {
        for (const field of LINE_FIELDS) {
          const message = lineErrors[field]?.message;
          if (typeof message === "string") {
            items.push({
              fieldId: fieldId(`lines.${String(index)}.${field}`),
              message: t("documents.lineError", { number: index + 1, message }),
            });
          }
        }
      });
      continue;
    }
    const message = errors[name]?.message;
    if (typeof message === "string") items.push({ fieldId: fieldId(name), message });
  }
  return items;
}
