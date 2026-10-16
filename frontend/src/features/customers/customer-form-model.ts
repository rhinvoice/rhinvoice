import type { Path } from "react-hook-form";
import { z } from "zod";

import type { Customer, CustomerRequest } from "@/features/customers/api";
import { fields, toApiDecimal } from "@/features/shared/form-schema";
import { DOCUMENT_LANGUAGES } from "@/features/shared/document-languages";
import { formatDecimalInput } from "@/lib/format";
import type { T } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";

export type CountryCode = CustomerRequest["address"]["country"];

/** Values come from a select with the API's country list, so the shape check suffices. */
const countryCode = z.custom<CountryCode>(
  (value) => typeof value === "string" && /^[A-Z]{2}$/.test(value),
);

export function customerSchema(t: T, locale: Locale) {
  const f = fields(t, locale);
  const address = {
    street: f.optionalText(70),
    house_number: f.optionalText(16),
    supplement: f.optionalText(70),
    postal_code: f.optionalText(16),
    city: f.optionalText(35),
    country: countryCode,
  };
  return z
    .object({
      kind: z.enum(["company", "person"]),
      number: f.optionalText(20),
      company_name: f.optionalText(70),
      salutation: f.optionalText(50),
      first_name: f.optionalText(50),
      last_name: f.optionalText(50),
      contact_person: f.optionalText(70),
      ...address,
      has_delivery: z.boolean(),
      delivery_street: address.street,
      delivery_house_number: address.house_number,
      delivery_supplement: address.supplement,
      delivery_postal_code: address.postal_code,
      delivery_city: address.city,
      delivery_country: address.country,
      email: f.email,
      phone: f.optionalText(50),
      vat_number: f.vatNumber,
      group: f.optionalText(50),
      default_currency: z.enum(["", "CHF", "EUR"]),
      default_language: z.enum(["", ...DOCUMENT_LANGUAGES]),
      tax_exempt: z.boolean(),
      default_discount: f.decimal({ max: 100, decimals: 2 }),
      payment_terms_days: f.days,
      note: f.optionalText(4000),
    })
    .superRefine((values, context) => {
      const required = (path: string) => {
        context.addIssue({ code: "custom", path: [path], message: t("validation.required") });
      };
      if (values.kind === "company" && values.company_name === "") required("company_name");
      if (values.kind === "person" && values.last_name === "") required("last_name");
      if (values.postal_code === "") required("postal_code");
      if (values.city === "") required("city");
      if (values.has_delivery) {
        if (values.delivery_postal_code === "") required("delivery_postal_code");
        if (values.delivery_city === "") required("delivery_city");
      }
    });
}

export type CustomerFormValues = z.infer<ReturnType<typeof customerSchema>>;

/** Field order for the error summary (matches the visual order of the form). */
export const CUSTOMER_FIELD_ORDER: readonly (keyof CustomerFormValues)[] = [
  "number",
  "company_name",
  "salutation",
  "first_name",
  "last_name",
  "contact_person",
  "street",
  "house_number",
  "supplement",
  "postal_code",
  "city",
  "email",
  "phone",
  "vat_number",
  "default_discount",
  "payment_terms_days",
  "delivery_street",
  "delivery_postal_code",
  "delivery_city",
  "note",
];

export function emptyCustomer(country: CountryCode): CustomerFormValues {
  return {
    kind: "company",
    number: "",
    company_name: "",
    salutation: "",
    first_name: "",
    last_name: "",
    contact_person: "",
    street: "",
    house_number: "",
    supplement: "",
    postal_code: "",
    city: "",
    country,
    has_delivery: false,
    delivery_street: "",
    delivery_house_number: "",
    delivery_supplement: "",
    delivery_postal_code: "",
    delivery_city: "",
    delivery_country: country,
    email: "",
    phone: "",
    vat_number: "",
    group: "",
    default_currency: "",
    default_language: "",
    tax_exempt: false,
    default_discount: "",
    payment_terms_days: "",
    note: "",
  };
}

export function customerToForm(customer: Customer, locale: Locale): CustomerFormValues {
  const delivery = customer.delivery_address;
  return {
    kind: customer.kind,
    number: customer.number,
    company_name: customer.company_name,
    salutation: customer.salutation,
    first_name: customer.first_name,
    last_name: customer.last_name,
    contact_person: customer.contact_person,
    street: customer.address.street,
    house_number: customer.address.house_number,
    supplement: customer.address.supplement,
    postal_code: customer.address.postal_code,
    city: customer.address.city,
    country: customer.address.country,
    has_delivery: delivery !== null,
    delivery_street: delivery?.street ?? "",
    delivery_house_number: delivery?.house_number ?? "",
    delivery_supplement: delivery?.supplement ?? "",
    delivery_postal_code: delivery?.postal_code ?? "",
    delivery_city: delivery?.city ?? "",
    delivery_country: delivery?.country ?? customer.address.country,
    email: customer.email ?? "",
    phone: customer.phone,
    vat_number: customer.vat_number ?? "",
    group: customer.group,
    default_currency: customer.default_currency ?? "",
    default_language: customer.default_language ?? "",
    tax_exempt: customer.tax_exempt,
    default_discount:
      customer.default_discount === "0"
        ? ""
        : formatDecimalInput(customer.default_discount, locale, 0, 2),
    payment_terms_days:
      customer.payment_terms_days === null ? "" : String(customer.payment_terms_days),
    note: customer.note,
  };
}

export function formToRequest(values: CustomerFormValues, locale: Locale): CustomerRequest {
  return {
    kind: values.kind,
    number: values.number,
    company_name: values.kind === "company" ? values.company_name : "",
    salutation: values.salutation,
    first_name: values.first_name,
    last_name: values.last_name,
    contact_person: values.kind === "company" ? values.contact_person : "",
    address: {
      street: values.street,
      house_number: values.house_number,
      supplement: values.supplement,
      postal_code: values.postal_code,
      city: values.city,
      country: values.country,
    },
    delivery_address: values.has_delivery
      ? {
          street: values.delivery_street,
          house_number: values.delivery_house_number,
          supplement: values.delivery_supplement,
          postal_code: values.delivery_postal_code,
          city: values.delivery_city,
          country: values.delivery_country,
        }
      : null,
    email: values.email === "" ? null : values.email,
    phone: values.phone,
    vat_number: values.vat_number === "" ? null : values.vat_number,
    group: values.group,
    default_currency: values.default_currency === "" ? null : values.default_currency,
    default_language: values.default_language === "" ? null : values.default_language,
    tax_exempt: values.tax_exempt,
    default_discount:
      values.default_discount === "" ? "0" : toApiDecimal(values.default_discount, locale),
    payment_terms_days: values.payment_terms_days === "" ? null : Number(values.payment_terms_days),
    note: values.note,
  };
}

/** Map API validation keys ("address.city", "delivery_address.city") to form fields. */
export function customerFieldFor(apiField: string): Path<CustomerFormValues> | null {
  const [head, tail] = apiField.split(".");
  if (head === "address" && tail !== undefined) return tail as Path<CustomerFormValues>;
  if (head === "delivery_address" && tail !== undefined)
    return `delivery_${tail}` as Path<CustomerFormValues>;
  const known = new Set<string>(Object.keys(emptyCustomer("CH")));
  if (head !== undefined && known.has(head)) return head as Path<CustomerFormValues>;
  return null;
}

/** The member states of the European Union (ISO 3166-1 alpha-2). */
export const EU_COUNTRIES: ReadonlySet<string> = new Set([
  "AT",
  "BE",
  "BG",
  "CY",
  "CZ",
  "DE",
  "DK",
  "EE",
  "ES",
  "FI",
  "FR",
  "GR",
  "HR",
  "HU",
  "IE",
  "IT",
  "LT",
  "LU",
  "LV",
  "MT",
  "NL",
  "PL",
  "PT",
  "RO",
  "SE",
  "SI",
  "SK",
]);

/**
 * A business in the EU with a VAT number is invoiced with reverse charge by
 * itself; marked tax exempt it would get an exempt invoice instead. Exemption
 * is meant for customers exempt from VAT, such as embassies.
 */
export function exemptInsteadOfReverseCharge(values: {
  readonly kind: string;
  readonly country: string;
  readonly vat_number: string;
  readonly tax_exempt: boolean;
}): boolean {
  return (
    values.tax_exempt &&
    values.kind === "company" &&
    values.vat_number.trim() !== "" &&
    EU_COUNTRIES.has(values.country)
  );
}
