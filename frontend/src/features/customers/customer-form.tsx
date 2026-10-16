import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm, useWatch } from "react-hook-form";

import { useI18n } from "@/components/i18n/use-i18n";
import { ErrorSummary } from "@/components/ui/error-summary";
import { Field } from "@/components/ui/field";
import { Fieldset } from "@/components/ui/fieldset";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { RadioCard } from "@/components/ui/radio-cards";
import { Switch } from "@/components/ui/switch";
import { useSaveShortcut } from "@/components/use-key-shortcuts";
import {
  CUSTOMER_FIELD_ORDER,
  customerFieldFor,
  customerSchema,
  exemptInsteadOfReverseCharge,
  type CustomerFormValues,
} from "@/features/customers/customer-form-model";
import { AddressFields } from "@/features/shared/address-fields";
import { DOCUMENT_LANGUAGES } from "@/features/shared/document-languages";
import { FormAlert } from "@/features/shared/form-alert";
import { summaryItems } from "@/features/shared/form-errors";
import { FormFooter } from "@/features/shared/form-footer";
import { applyServerErrors } from "@/features/shared/server-errors";
import { useErrorMessage } from "@/features/shared/use-error-message";

interface CustomerFormProps {
  readonly defaultValues: CustomerFormValues;
  readonly onSubmit: (values: CustomerFormValues) => Promise<unknown>;
  readonly submitLabel?: string;
}

export function CustomerForm({ defaultValues, onSubmit, submitLabel }: CustomerFormProps) {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const form = useForm<CustomerFormValues>({
    resolver: zodResolver(customerSchema(t, locale)),
    mode: "onTouched",
    shouldFocusError: false,
    defaultValues,
  });
  const { errors, isSubmitted, submitCount, isSubmitting, isDirty } = form.formState;
  const kind = useWatch({ control: form.control, name: "kind" });
  const hasDelivery = useWatch({ control: form.control, name: "has_delivery" });
  const country = useWatch({ control: form.control, name: "country" });
  const vatNumber = useWatch({ control: form.control, name: "vat_number" });
  const taxExempt = useWatch({ control: form.control, name: "tax_exempt" });
  const error = (name: keyof CustomerFormValues) => errors[name]?.message;

  const submit = form.handleSubmit(async (values) => {
    try {
      await onSubmit(values);
      form.reset(values);
    } catch (caught) {
      const attached = applyServerErrors(caught, form.setError, t, customerFieldFor);
      if (!attached) {
        form.setError("root", { type: "server", message: errorMessage(caught) ?? "" });
      }
    }
  });
  useSaveShortcut(() => void submit());

  return (
    <form
      className="flex max-w-2xl flex-col gap-8"
      onSubmit={(event) => void submit(event)}
      noValidate
    >
      {isSubmitted ? (
        <ErrorSummary
          title={t("validation.summary", {
            count: summaryItems(errors, CUSTOMER_FIELD_ORDER).length,
          })}
          items={summaryItems(errors, CUSTOMER_FIELD_ORDER)}
          submitCount={submitCount}
        />
      ) : null}
      <FormAlert message={errors.root?.message ?? null} />

      <Fieldset legend={t("customers.sectionBasics")}>
        <fieldset className="flex flex-col gap-1.5">
          <legend className="mb-1.5 text-sm font-medium">{t("customers.kind")}</legend>
          <div className="grid grid-cols-2 gap-2 sm:max-w-sm">
            <RadioCard
              id="kind-company"
              value="company"
              label={t("customers.kindCompany")}
              {...form.register("kind")}
            />
            <RadioCard
              id="kind-person"
              value="person"
              label={t("customers.kindPerson")}
              {...form.register("kind")}
            />
          </div>
        </fieldset>
        {kind === "company" ? (
          <>
            <Field label={t("customers.companyName")} error={error("company_name")}>
              <Input
                id="company_name"
                autoComplete="organization"
                {...form.register("company_name")}
              />
            </Field>
            <Field
              label={t("customers.contactPerson")}
              description={t("customers.contactPersonHint")}
              error={error("contact_person")}
              optionalLabel={t("common.optional")}
            >
              <Input id="contact_person" autoComplete="name" {...form.register("contact_person")} />
            </Field>
          </>
        ) : (
          <div className="grid gap-4 sm:grid-cols-[8rem_1fr_1fr]">
            <Field
              label={t("customers.salutation")}
              error={error("salutation")}
              optionalLabel={t("common.optional")}
            >
              <Input
                id="salutation"
                autoComplete="honorific-prefix"
                {...form.register("salutation")}
              />
            </Field>
            <Field
              label={t("customers.firstName")}
              error={error("first_name")}
              optionalLabel={t("common.optional")}
            >
              <Input id="first_name" autoComplete="given-name" {...form.register("first_name")} />
            </Field>
            <Field label={t("customers.lastName")} error={error("last_name")}>
              <Input id="last_name" autoComplete="family-name" {...form.register("last_name")} />
            </Field>
          </div>
        )}
        <Field
          label={t("customers.numberLabel")}
          description={t("customers.numberHint")}
          error={error("number")}
          optionalLabel={t("common.optional")}
        >
          <Input id="number" className="sm:max-w-48" {...form.register("number")} />
        </Field>
      </Fieldset>

      <Fieldset legend={t("address.legend")}>
        <AddressFields
          names={{
            street: "street",
            house_number: "house_number",
            supplement: "supplement",
            postal_code: "postal_code",
            city: "city",
            country: "country",
          }}
          register={form.register}
          errors={errors}
        />
      </Fieldset>

      <Fieldset legend={t("customers.sectionContact")}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label={t("customers.email")}
            error={error("email")}
            optionalLabel={t("common.optional")}
          >
            <Input
              id="email"
              type="email"
              autoComplete="email"
              inputMode="email"
              {...form.register("email")}
            />
          </Field>
          <Field
            label={t("customers.phone")}
            error={error("phone")}
            optionalLabel={t("common.optional")}
          >
            <Input id="phone" type="tel" autoComplete="tel" {...form.register("phone")} />
          </Field>
        </div>
      </Fieldset>

      <Fieldset legend={t("customers.sectionBilling")}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            className="sm:col-span-2"
            label={t("customers.vatNumber")}
            description={t("customers.vatNumberHint")}
            error={error("vat_number")}
            optionalLabel={t("common.optional")}
          >
            <Input id="vat_number" {...form.register("vat_number")} />
          </Field>
          <Field label={t("customers.defaultCurrency")} error={error("default_currency")}>
            <NativeSelect id="default_currency" {...form.register("default_currency")}>
              <option value="">{t("common.useDefault")}</option>
              <option value="CHF">CHF</option>
              <option value="EUR">EUR</option>
            </NativeSelect>
          </Field>
          <Field label={t("customers.defaultLanguage")} error={error("default_language")}>
            <NativeSelect id="default_language" {...form.register("default_language")}>
              <option value="">{t("common.useDefault")}</option>
              {DOCUMENT_LANGUAGES.map((language) => (
                <option key={language} value={language}>
                  {t(`language.${language}`)}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field
            label={t("customers.defaultDiscount")}
            error={error("default_discount")}
            optionalLabel={t("common.optional")}
          >
            <Input
              id="default_discount"
              inputMode="decimal"
              className="tabular-nums"
              {...form.register("default_discount")}
            />
          </Field>
          <Field
            label={t("customers.paymentTerms")}
            description={t("customers.paymentTermsHint")}
            error={error("payment_terms_days")}
            optionalLabel={t("common.optional")}
          >
            <Input
              id="payment_terms_days"
              inputMode="numeric"
              className="tabular-nums"
              {...form.register("payment_terms_days")}
            />
          </Field>
          <Field
            label={t("customers.group")}
            error={error("group")}
            optionalLabel={t("common.optional")}
          >
            <Input id="group" {...form.register("group")} />
          </Field>
        </div>
        <Controller
          control={form.control}
          name="tax_exempt"
          render={({ field }) => (
            <div className="flex items-start justify-between gap-4">
              <div className="flex flex-col gap-1">
                <Label htmlFor="tax_exempt">{t("customers.taxExempt")}</Label>
                <p id="tax_exempt-hint" className="text-sm text-muted-foreground">
                  {t("customers.taxExemptHint")}
                </p>
              </div>
              <Switch
                id="tax_exempt"
                checked={field.value}
                onCheckedChange={field.onChange}
                aria-describedby="tax_exempt-hint"
              />
            </div>
          )}
        />
        {exemptInsteadOfReverseCharge({
          kind,
          country,
          vat_number: vatNumber,
          tax_exempt: taxExempt,
        }) ? (
          <p role="status" className="rounded-md bg-warning/15 p-3 text-sm">
            {t("customers.taxExemptReverseCharge")}
          </p>
        ) : null}
      </Fieldset>

      <Fieldset legend={t("customers.sectionDelivery")}>
        <Controller
          control={form.control}
          name="has_delivery"
          render={({ field }) => (
            <div className="flex items-center justify-between gap-4">
              <Label htmlFor="has_delivery">{t("customers.hasDelivery")}</Label>
              <Switch id="has_delivery" checked={field.value} onCheckedChange={field.onChange} />
            </div>
          )}
        />
        {hasDelivery ? (
          <AddressFields
            names={{
              street: "delivery_street",
              house_number: "delivery_house_number",
              supplement: "delivery_supplement",
              postal_code: "delivery_postal_code",
              city: "delivery_city",
              country: "delivery_country",
            }}
            register={form.register}
            errors={errors}
          />
        ) : null}
      </Fieldset>

      <Field
        label={t("customers.note")}
        description={t("customers.noteHint")}
        error={error("note")}
        optionalLabel={t("common.optional")}
      >
        <Textarea id="note" rows={4} {...form.register("note")} />
      </Field>

      <FormFooter
        saving={isSubmitting}
        dirty={isDirty}
        {...(submitLabel === undefined ? {} : { label: submitLabel })}
      />
    </form>
  );
}
