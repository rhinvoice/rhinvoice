import { useQuery } from "@tanstack/react-query";
import { useFormContext, useWatch } from "react-hook-form";

import { useI18n } from "@/components/i18n/use-i18n";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { customerOptionQuery } from "@/features/documents/api";
import { fieldId, type DocumentFormValues } from "@/features/documents/document-form-model";
import { printLayoutsQuery } from "@/features/shared/company-api";
import { cn } from "@/lib/cn";
import { MAX_FIELD_VALUE, entryName, fieldEntries, type InfoRow } from "@/lib/info-block";
import { layoutFor } from "@/lib/print-layouts";
import { referenceHint } from "@/lib/xrechnung";

/** The layouts, and the one the document prints with: its own, its customer's or the default. */
function useDocumentLayout() {
  const { control } = useFormContext<DocumentFormValues>();
  const chosen = useWatch({ control, name: "print_layout_id" });
  const customerId = useWatch({ control, name: "customer_id" });
  const layouts = useQuery(printLayoutsQuery).data ?? [];
  const customer = useQuery({ ...customerOptionQuery(customerId), enabled: customerId !== "" });
  const customers = customerId === "" ? null : (customer.data?.print_layout_id ?? null);
  return {
    layouts,
    layout: layoutFor(layouts, chosen === "" ? null : chosen, customers),
    automatic: layoutFor(layouts, null, customers),
    fromCustomer: customers !== null && layouts.some((named) => named.id === customers),
  };
}

/**
 * Everything the document prints top right that is entered here: the service period, the
 * reference and the print layout's fields, such as a project or a cost centre (#62).
 *
 * A row the layout hides stays to be filled in: the e-invoice carries it all the same (and
 * the date of supply decides the VAT rate). Only fields of the document's layout are shown;
 * values of fields it does not list stay with the document and come back with a layout that
 * lists them. Plans set the service period themselves.
 */
export function InfoInputs({ plan }: { readonly plan: boolean }) {
  const { t } = useI18n();
  const { register, formState, control } = useFormContext<DocumentFormValues>();
  const errors = formState.errors;
  const { layout } = useDocumentLayout();
  const customerId = useWatch({ control, name: "customer_id" });
  const customer = useQuery({ ...customerOptionQuery(customerId), enabled: customerId !== "" });
  const hint = referenceHint(customerId === "" ? undefined : customer.data);
  const entries = layout === undefined ? [] : layout.layout.info_block;
  const hidden = (key: InfoRow) => entries.some((entry) => entry.key === key && !entry.shown);
  const onlyEInvoice = (key: InfoRow) => (hidden(key) ? t("documents.onlyInEInvoice") : null);
  return (
    <div className="grid gap-4 @md:grid-cols-2">
      {plan ? (
        <p className="text-sm text-muted-foreground @md:col-span-2">
          {t("recurring.servicePeriodByPlan")}
        </p>
      ) : (
        <>
          <Field
            label={t("documents.serviceFrom")}
            error={errors.service_from?.message}
            optionalLabel={t("common.optional")}
          >
            <Input id={fieldId("service_from")} type="date" {...register("service_from")} />
          </Field>
          <Field
            label={t("documents.serviceTo")}
            description={[t("documents.serviceHint"), onlyEInvoice("service_date")]
              .filter(Boolean)
              .join(" ")}
            error={errors.service_to?.message}
            optionalLabel={t("common.optional")}
          >
            <Input id={fieldId("service_to")} type="date" {...register("service_to")} />
          </Field>
        </>
      )}
      <Field
        className="@md:col-span-2"
        label={t("documents.reference")}
        description={[t(hint.key, { value: hint.value }), onlyEInvoice("reference")]
          .filter(Boolean)
          .join(" ")}
        error={errors.reference?.message}
        optionalLabel={t("common.optional")}
      >
        <Input id={fieldId("reference")} {...register("reference")} />
      </Field>
      {fieldEntries(entries).map((entry) => (
        <Field
          key={entry.key}
          label={entryName(entry, t)}
          error={errors.fields?.[entry.key]?.message}
          optionalLabel={t("common.optional")}
        >
          <Input
            id={fieldId(`fields.${entry.key}`)}
            maxLength={MAX_FIELD_VALUE}
            {...register(`fields.${entry.key}`)}
          />
        </Field>
      ))}
    </div>
  );
}

/**
 * The print layout of the document, above the preview (#48, variant 5B); shown with more than
 * one layout. "Automatic" names the customer's layout or the default.
 */
export function LayoutChoice({ className }: { readonly className?: string }) {
  const { t } = useI18n();
  const { register, control } = useFormContext<DocumentFormValues>();
  const chosen = useWatch({ control, name: "print_layout_id" });
  const { layouts, automatic, fromCustomer } = useDocumentLayout();
  if (layouts.length < 2 || automatic === undefined) return null;
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <label htmlFor={fieldId("print_layout_id")} className="text-sm font-medium">
        {t("documents.printLayout")}
      </label>
      <NativeSelect
        id={fieldId("print_layout_id")}
        className="w-auto min-w-48"
        {...register("print_layout_id")}
      >
        <option value="">
          {fromCustomer
            ? t("documents.printLayoutFromCustomer", { name: automatic.name })
            : t("documents.printLayoutDefault", { name: automatic.name })}
        </option>
        {layouts
          // The automatic one is the first option; listed again only when chosen by name.
          .filter((named) => named.id !== automatic.id || named.id === chosen)
          .map((named) => (
            <option key={named.id} value={named.id}>
              {named.name}
            </option>
          ))}
      </NativeSelect>
    </div>
  );
}
