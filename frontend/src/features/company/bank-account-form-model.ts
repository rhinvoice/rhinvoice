import { z } from "zod";

import type { BankAccount, BankAccountRequest } from "@/features/company/api";
import { fields } from "@/features/shared/form-schema";
import type { T } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";
import { ibanProblem, isQrIban, isValidBic, normalizeIban } from "@/lib/validation/iban";

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
    })
    .superRefine((values, context) => {
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

export function emptyBankAccount(currency: "CHF" | "EUR", holder: string): BankAccountFormValues {
  return { currency, bank_name: "", holder, iban: "", qr_iban: "", bic: "", is_default: false };
}

export function bankAccountToForm(account: BankAccount): BankAccountFormValues {
  return {
    currency: account.currency,
    bank_name: account.bank_name,
    holder: account.holder,
    iban: account.iban_formatted,
    qr_iban: account.qr_iban ?? "",
    bic: account.bic ?? "",
    is_default: account.is_default,
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
  };
}
