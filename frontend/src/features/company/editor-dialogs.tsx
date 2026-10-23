import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useSaveCompany } from "@/features/company/api";
import { BankAccountDialog } from "@/features/company/bank-accounts-settings";
import { emptyBankAccount } from "@/features/company/bank-account-form-model";
import {
  companyFieldFor,
  companySchema,
  companyToForm,
  formToRequest,
  type CompanyFormValues,
} from "@/features/company/company-form-model";
import { SwitchRow } from "@/features/company/switch-row";
import { companyQuery, type Company } from "@/features/shared/company-api";
import { asksTaxNumber, termsFor } from "@/features/shared/country-profile-model";
import { FormAlert } from "@/features/shared/form-alert";
import { applyServerErrors } from "@/features/shared/server-errors";
import { useErrorMessage } from "@/features/shared/use-error-message";

/** A new bank account in ``currency``, held by the company. */
export function NewBankAccountDialog({
  currency,
  onClose,
}: {
  readonly currency: "CHF" | "EUR";
  readonly onClose: () => void;
}) {
  const company = useQuery(companyQuery).data;
  if (company === undefined) return null;
  return (
    <BankAccountDialog
      account={null}
      defaults={emptyBankAccount(currency, company?.name ?? "")}
      profile={company?.profile}
      onClose={onClose}
    />
  );
}

/** The company's tax IDs and VAT registration, which invoices state. */
export function CompanyTaxDialog({ onClose }: { readonly onClose: () => void }) {
  const company = useQuery(companyQuery).data;
  if (company === undefined || company === null) return null;
  return <CompanyTaxForm company={company} onClose={onClose} />;
}

function CompanyTaxForm({
  company,
  onClose,
}: {
  readonly company: Company;
  readonly onClose: () => void;
}) {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const save = useSaveCompany();
  const form = useForm<CompanyFormValues>({
    resolver: zodResolver(companySchema(t, locale)),
    mode: "onTouched",
    defaultValues: companyToForm(company),
  });
  const { errors, isSubmitting } = form.formState;
  const terms = termsFor(company.profile, locale);
  const submit = form.handleSubmit(
    async (values) => {
      try {
        await save.mutateAsync(formToRequest(values));
        toast.success(t("common.saved"));
        onClose();
      } catch (caught) {
        if (!applyServerErrors(caught, form.setError, t, companyFieldFor)) {
          form.setError("root", { type: "server", message: errorMessage(caught) ?? "" });
        }
      }
    },
    // Only these fields are shown: anything else wrong belongs to the company settings.
    (invalid) => {
      if (invalid.vat_number === undefined && invalid.tax_number === undefined) {
        form.setError("root", { type: "client", message: t("company.taxDialogOtherErrors") });
      }
    },
  );

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent closeLabel={t("common.close")}>
        <DialogHeader>
          <DialogTitle>{t("company.taxDialogTitle")}</DialogTitle>
          <DialogDescription>{t("company.taxDialogHint")}</DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={(event) => void submit(event)} noValidate>
          <FormAlert message={errors.root?.message ?? null} />
          <Field
            label={terms.vat_number_field}
            description={terms.vat_number_hint}
            error={errors.vat_number?.message}
            optionalLabel={t("common.optional")}
          >
            <Input id="vat_number" {...form.register("vat_number")} />
          </Field>
          {asksTaxNumber(company.profile, company.tax_number) ? (
            <Field
              label={t("company.taxNumber")}
              description={t("company.taxNumberHint")}
              error={errors.tax_number?.message}
              optionalLabel={t("common.optional")}
            >
              <Input id="tax_number" {...form.register("tax_number")} />
            </Field>
          ) : null}
          <Controller
            control={form.control}
            name="small_business"
            render={({ field }) => (
              <SwitchRow
                id="small_business"
                label={terms.small_business}
                hint={t("company.smallBusinessHint")}
                checked={field.value}
                onChange={field.onChange}
              />
            )}
          />
          <DialogFooter>
            <Button variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {t("common.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
