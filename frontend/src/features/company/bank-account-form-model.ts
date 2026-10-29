import type { Path } from "react-hook-form";
import { z } from "zod";

import type { BankAccount, BankAccountRequest } from "@/features/company/api";
import { fields } from "@/features/shared/form-schema";
import type { T } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";
import { ibanProblem, isQrIban, isValidBic, normalizeIban } from "@/lib/validation/iban";

type CountryCode = NonNullable<BankAccountRequest["holder_address"]>["country"];

/** Values come from a select with the API's country list, so the shape check suffices. */
const countryCode = z.custom<CountryCode>(
  (value) => typeof value === "string" && /^[A-Z]{2}$/.test(value),
);

export function bankAccountSchema(t: T, locale: Locale) {
  const f = fields(t, locale);
  return z
    .object({
      currency: z.enum(["CHF", "EUR"]),
      bank_name: f.requiredText(70),
      holder: f.requiredText(70),
      iban: f.iban.refine((value) => value !== "", t("validation.required")),
      qr_iban: z.string().trim(),
      bic: z
        .string()
        .trim()
        .refine((value) => value === "" || isValidBic(value), t("validation.bic")),
      is_default: z.boolean(),
      third_party: z.boolean(),
      holder_street: f.optionalText(70),
      holder_house_number: f.optionalText(16),
      holder_supplement: f.optionalText(70),
      holder_postal_code: f.optionalText(16),
      holder_city: f.optionalText(35),
      holder_country: countryCode,
    })
    .superRefine((values, context) => {
      if (values.third_party) {
        for (const path of ["holder_postal_code", "holder_city"] as const) {
          if (values[path] === "")
            context.addIssue({ code: "custom", path: [path], message: t("validation.required") });
        }
      }
      if (values.qr_iban === "") return;
      const problem = ibanProblem(values.qr_iban);
      const message =
        problem !== null
          ? t(`validation.iban.${problem === "length" ? "checksum" : problem}`)
          : isQrIban(values.qr_iban)
            ? null
            : t("validation.iban.notQr");
      if (message !== null) context.addIssue({ code: "custom", path: ["qr_iban"], message });
    });
}

export type BankAccountFormValues = z.infer<ReturnType<typeof bankAccountSchema>>;

/** A new account; a third party's address starts in the company's country. */
export function emptyBankAccount(
  currency: "CHF" | "EUR",
  holder: string,
  country: CountryCode = "CH",
): BankAccountFormValues {
  return {
    currency,
    bank_name: "",
    holder,
    iban: "",
    qr_iban: "",
    bic: "",
    is_default: false,
    third_party: false,
    holder_street: "",
    holder_house_number: "",
    holder_supplement: "",
    holder_postal_code: "",
    holder_city: "",
    holder_country: country,
  };
}

export function bankAccountToForm(
  account: BankAccount,
  country: CountryCode = "CH",
): BankAccountFormValues {
  const address = account.holder_address;
  return {
    currency: account.currency,
    bank_name: account.bank_name,
    holder: account.holder,
    iban: account.iban_formatted,
    qr_iban: account.qr_iban ?? "",
    bic: account.bic ?? "",
    is_default: account.is_default,
    third_party: account.third_party,
    holder_street: address?.street ?? "",
    holder_house_number: address?.house_number ?? "",
    holder_supplement: address?.supplement ?? "",
    holder_postal_code: address?.postal_code ?? "",
    holder_city: address?.city ?? "",
    holder_country: address?.country ?? country,
  };
}

export function formToRequest(values: BankAccountFormValues): BankAccountRequest {
  return {
    currency: values.currency,
    bank_name: values.bank_name,
    holder: values.holder,
    iban: normalizeIban(values.iban),
    qr_iban: values.qr_iban === "" ? null : normalizeIban(values.qr_iban),
    bic: values.bic === "" ? null : values.bic.replace(/\s+/g, "").toUpperCase(),
    is_default: values.is_default,
    third_party: values.third_party,
    holder_address: values.third_party
      ? {
          street: values.holder_street,
          house_number: values.holder_house_number,
          supplement: values.holder_supplement,
          postal_code: values.holder_postal_code,
          city: values.holder_city,
          country: values.holder_country,
        }
      : null,
  };
}

/** Map API validation keys ("holder_address.city", "iban") to form fields. */
export function bankAccountFieldFor(apiField: string): Path<BankAccountFormValues> | null {
  const [head, tail] = apiField.split(".");
  // The domain names the missing address as a whole: the postal code is its first field.
  if (head === "holder_address")
    return tail === undefined
      ? "holder_postal_code"
      : (`holder_${tail}` as Path<BankAccountFormValues>);
  const known = new Set<string>(Object.keys(emptyBankAccount("CHF", "")));
  return head !== undefined && known.has(head) ? (head as Path<BankAccountFormValues>) : null;
}
