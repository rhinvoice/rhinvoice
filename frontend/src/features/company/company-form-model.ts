import type { Path } from "react-hook-form";
import { z } from "zod";

import type { Company, CompanyRequest } from "@/features/company/api";
import { fields } from "@/features/shared/form-schema";
import { DOCUMENT_LANGUAGES } from "@/features/shared/document-languages";
import type { T } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";

/** The company countries with a profile; checked against the backend (test_frontend_sync). */
export const COMPANY_COUNTRIES = ["CH", "LI", "DE", "AT"] as const;

export function companySchema(t: T, locale: Locale) {
  const f = fields(t, locale);
  return z.object({
    name: f.requiredText(70),
    street: f.optionalText(70),
    house_number: f.optionalText(16),
    supplement: f.optionalText(70),
    postal_code: f.requiredText(16),
    city: f.requiredText(35),
    country: z.enum(COMPANY_COUNTRIES),
    email: f.email,
    phone: f.optionalText(100),
    website: f.optionalText(100),
    vat_number: f.vatNumber,
    tax_number: f.optionalText(100),
    commercial_register: f.optionalText(200),
    small_business: z.boolean(),
    cash_rounding: z.boolean(),
    default_currency: z.enum(["CHF", "EUR"]),
    default_language: z.enum(DOCUMENT_LANGUAGES),
    payment_terms_days: z
      .string()
      .trim()
      .regex(/^\d{1,3}$/, t("validation.days"))
      .refine((v) => Number(v) <= 365, t("validation.days")),
    accent_hue: z.number().int().min(0).max(359),
  });
}

export type CompanyFormValues = z.infer<ReturnType<typeof companySchema>>;

export const COMPANY_FIELD_ORDER: readonly (keyof CompanyFormValues)[] = [
  "name",
  "street",
  "house_number",
  "supplement",
  "postal_code",
  "city",
  "email",
  "phone",
  "website",
  "vat_number",
  "tax_number",
  "commercial_register",
  "payment_terms_days",
];

export function emptyCompany(
  country: (typeof COMPANY_COUNTRIES)[number],
  currency: CompanyFormValues["default_currency"],
): CompanyFormValues {
  return {
    name: "",
    street: "",
    house_number: "",
    supplement: "",
    postal_code: "",
    city: "",
    country,
    email: "",
    phone: "",
    website: "",
    vat_number: "",
    tax_number: "",
    commercial_register: "",
    small_business: false,
    // Off for everyone: the 5-centime rounding is a choice (Settings → Company).
    cash_rounding: false,
    default_currency: currency,
    default_language: "de",
    payment_terms_days: "30",
    accent_hue: 250,
  };
}

export function companyToForm(company: Company): CompanyFormValues {
  return {
    name: company.name,
    street: company.address.street,
    house_number: company.address.house_number,
    supplement: company.address.supplement,
    postal_code: company.address.postal_code,
    city: company.address.city,
    country: company.country,
    email: company.email ?? "",
    phone: company.phone,
    website: company.website,
    vat_number: company.vat_number ?? "",
    tax_number: company.tax_number,
    commercial_register: company.commercial_register,
    small_business: company.small_business,
    cash_rounding: company.cash_rounding,
    default_currency: company.default_currency,
    default_language: company.default_language,
    payment_terms_days: String(company.payment_terms_days),
    accent_hue: company.accent_hue,
  };
}

export function formToRequest(values: CompanyFormValues): CompanyRequest {
  return {
    name: values.name,
    address: {
      street: values.street,
      house_number: values.house_number,
      supplement: values.supplement,
      postal_code: values.postal_code,
      city: values.city,
      country: values.country,
    },
    email: values.email === "" ? null : values.email,
    phone: values.phone,
    website: values.website,
    vat_number: values.vat_number === "" ? null : values.vat_number,
    tax_number: values.tax_number,
    commercial_register: values.commercial_register,
    small_business: values.small_business,
    cash_rounding: values.cash_rounding,
    default_currency: values.default_currency,
    default_language: values.default_language,
    payment_terms_days: Number(values.payment_terms_days),
    accent_hue: values.accent_hue,
  };
}

export function companyFieldFor(apiField: string): Path<CompanyFormValues> | null {
  const [head, tail] = apiField.split(".");
  if (head === "address" && tail !== undefined) return tail as Path<CompanyFormValues>;
  return head !== undefined && head in emptyCompany("CH", "CHF")
    ? (head as Path<CompanyFormValues>)
    : null;
}
