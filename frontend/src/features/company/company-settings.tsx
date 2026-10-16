import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { ImageIcon, Trash2Icon, UploadIcon } from "lucide-react";
import { useEffect, useRef } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorSummary } from "@/components/ui/error-summary";
import { Field } from "@/components/ui/field";
import { Fieldset } from "@/components/ui/fieldset";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { useSaveShortcut } from "@/components/use-key-shortcuts";
import {
  logoQuery,
  useDeleteLogo,
  useSaveCompany,
  useUploadLogo,
  type Company,
} from "@/features/company/api";
import {
  COMPANY_COUNTRIES,
  COMPANY_FIELD_ORDER,
  companyFieldFor,
  companySchema,
  companyToForm,
  emptyCompany,
  formToRequest,
  type CompanyFormValues,
} from "@/features/company/company-form-model";
import { AddressFields } from "@/features/shared/address-fields";
import { DOCUMENT_LANGUAGES } from "@/features/shared/document-languages";
import { FormAlert } from "@/features/shared/form-alert";
import { summaryItems } from "@/features/shared/form-errors";
import { FormFooter } from "@/features/shared/form-footer";
import { applyServerErrors } from "@/features/shared/server-errors";
import { SwitchRow } from "@/features/company/switch-row";
import {
  asksTaxNumber,
  offersCashRounding,
  profileFor,
  termsFor,
} from "@/features/shared/country-profile-model";
import { countryProfilesQuery } from "@/features/shared/reference-api";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { applyAccentHue } from "@/lib/theme";
import { NotInDemo } from "@/features/shared/not-in-demo";

const MAX_LOGO_BYTES = 1024 * 1024;

export function CompanySettings({ company }: { readonly company: Company | null }) {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const save = useSaveCompany();
  const form = useForm<CompanyFormValues>({
    resolver: zodResolver(companySchema(t, locale)),
    mode: "onTouched",
    shouldFocusError: false,
    defaultValues: company === null ? emptyCompany("CH", "CHF") : companyToForm(company),
  });
  const { errors, isSubmitted, submitCount, isSubmitting, isDirty } = form.formState;
  const error = (name: keyof CompanyFormValues) => errors[name]?.message;
  const hue = useWatch({ control: form.control, name: "accent_hue" });
  const country = useWatch({ control: form.control, name: "country" });
  const roundingOn = useWatch({ control: form.control, name: "cash_rounding" });
  // Labels and fields follow the country chosen in the form; the saved company brings its
  // own profile, so nothing jumps while the list of all profiles loads.
  const profile = profileFor(useQuery(countryProfilesQuery).data, country, company?.profile);
  const terms = profile === undefined ? undefined : termsFor(profile, locale);
  const savedHue = company?.accent_hue;

  // Live preview of the accent colour; reverts to the saved value when leaving.
  useEffect(() => {
    applyAccentHue(document.documentElement, hue);
  }, [hue]);
  useEffect(
    () => () => {
      if (savedHue !== undefined) applyAccentHue(document.documentElement, savedHue);
    },
    [savedHue],
  );

  const submit = form.handleSubmit(async (values) => {
    try {
      await save.mutateAsync(formToRequest(values));
      form.reset(values);
      toast.success(t("company.saved"));
    } catch (caught) {
      if (!applyServerErrors(caught, form.setError, t, companyFieldFor)) {
        form.setError("root", { type: "server", message: errorMessage(caught) ?? "" });
      }
    }
  });
  useSaveShortcut(() => void submit());

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      {company === null ? <FormAlert message={t("company.setupHint")} /> : null}
      <NotInDemo title={t("company.logo")}>
        <LogoCard />
      </NotInDemo>
      <form className="flex flex-col gap-8" onSubmit={(event) => void submit(event)} noValidate>
        {isSubmitted ? (
          <ErrorSummary
            title={t("validation.summary", {
              count: summaryItems(errors, COMPANY_FIELD_ORDER).length,
            })}
            items={summaryItems(errors, COMPANY_FIELD_ORDER)}
            submitCount={submitCount}
          />
        ) : null}
        <FormAlert message={errors.root?.message ?? null} />
        <Fieldset legend={t("company.title")} description={t("company.description")}>
          <Field label={t("company.name")} error={error("name")}>
            <Input id="name" autoComplete="organization" {...form.register("name")} />
          </Field>
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
            countries={COMPANY_COUNTRIES}
          />
        </Fieldset>
        <Fieldset legend={t("company.sectionContact")}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label={t("company.email")}
              error={error("email")}
              optionalLabel={t("common.optional")}
            >
              <Input id="email" type="email" autoComplete="email" {...form.register("email")} />
            </Field>
            <Field
              label={t("company.phone")}
              error={error("phone")}
              optionalLabel={t("common.optional")}
            >
              <Input id="phone" type="tel" autoComplete="tel" {...form.register("phone")} />
            </Field>
            <Field
              className="sm:col-span-2"
              label={t("company.website")}
              error={error("website")}
              optionalLabel={t("common.optional")}
            >
              <Input id="website" type="url" autoComplete="url" {...form.register("website")} />
            </Field>
          </div>
        </Fieldset>
        <Fieldset legend={t("company.sectionTax")}>
          <Field
            label={terms?.vat_number_field ?? t("company.vatNumber")}
            description={terms?.vat_number_hint ?? t("company.vatNumberHint")}
            error={error("vat_number")}
            optionalLabel={t("common.optional")}
          >
            <Input id="vat_number" {...form.register("vat_number")} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            {asksTaxNumber(profile, company?.tax_number ?? "") ? (
              <Field
                label={t("company.taxNumber")}
                description={t("company.taxNumberHint")}
                error={error("tax_number")}
                optionalLabel={t("common.optional")}
              >
                <Input id="tax_number" {...form.register("tax_number")} />
              </Field>
            ) : null}
            <Field
              label={t("company.commercialRegister")}
              description={t("company.commercialRegisterHint")}
              error={error("commercial_register")}
              optionalLabel={t("common.optional")}
            >
              <Input id="commercial_register" {...form.register("commercial_register")} />
            </Field>
          </div>
          <Controller
            control={form.control}
            name="small_business"
            render={({ field }) => (
              <SwitchRow
                id="small_business"
                label={terms?.small_business ?? t("company.smallBusiness")}
                hint={t("company.smallBusinessHint")}
                checked={field.value}
                onChange={field.onChange}
              />
            )}
          />
        </Fieldset>
        <Fieldset legend={t("company.sectionDefaults")}>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label={t("company.defaultCurrency")} error={error("default_currency")}>
              <NativeSelect id="default_currency" {...form.register("default_currency")}>
                <option value="CHF">CHF</option>
                <option value="EUR">EUR</option>
              </NativeSelect>
            </Field>
            <Field label={t("company.defaultLanguage")} error={error("default_language")}>
              <NativeSelect id="default_language" {...form.register("default_language")}>
                {DOCUMENT_LANGUAGES.map((language) => (
                  <option key={language} value={language}>
                    {t(`language.${language}`)}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label={t("company.paymentTerms")} error={error("payment_terms_days")}>
              <Input
                id="payment_terms_days"
                inputMode="numeric"
                className="tabular-nums"
                {...form.register("payment_terms_days")}
              />
            </Field>
          </div>
          {offersCashRounding(profile, roundingOn) ? (
            <Controller
              control={form.control}
              name="cash_rounding"
              render={({ field }) => (
                <SwitchRow
                  id="cash_rounding"
                  label={t("company.cashRounding")}
                  hint={t("company.cashRoundingHint")}
                  checked={field.value}
                  onChange={field.onChange}
                />
              )}
            />
          ) : null}
        </Fieldset>
        <Fieldset legend={t("company.sectionAppearance")}>
          <Controller
            control={form.control}
            name="accent_hue"
            render={({ field }) => (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="accent_hue">{t("company.accentHue")}</Label>
                <div className="flex items-center gap-4">
                  <input
                    id="accent_hue"
                    type="range"
                    min={0}
                    max={359}
                    step={1}
                    value={field.value}
                    aria-describedby="accent_hue-hint"
                    onChange={(event) => {
                      field.onChange(Number(event.target.value));
                    }}
                    className="h-6 w-full max-w-sm accent-primary"
                  />
                  <span
                    className="size-8 shrink-0 rounded-md border bg-primary"
                    aria-hidden="true"
                  />
                  <output htmlFor="accent_hue" className="w-10 text-right text-sm tabular-nums">
                    {field.value}
                  </output>
                </div>
                <p id="accent_hue-hint" className="text-sm text-muted-foreground">
                  {t("company.accentHueHint")}
                </p>
              </div>
            )}
          />
        </Fieldset>
        <FormFooter saving={isSubmitting} dirty={isDirty} />
      </form>
    </div>
  );
}

function LogoCard() {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const logo = useQuery(logoQuery);
  const upload = useUploadLogo();
  const remove = useDeleteLogo();
  const input = useRef<HTMLInputElement>(null);
  const url = logo.data ?? null;

  const onFile = (file: File | undefined) => {
    if (file === undefined) return;
    if (file.size > MAX_LOGO_BYTES) {
      toast.error(t("company.logoTooLarge"));
      return;
    }
    upload.mutate(file, {
      onSuccess: () => toast.success(t("company.logoUploaded")),
      onError: (caught) => toast.error(errorMessage(caught)),
    });
  };

  return (
    <Card aria-labelledby="logo-title">
      <CardHeader>
        <CardTitle id="logo-title">{t("company.logo")}</CardTitle>
        <CardDescription>{t("company.logoHint")}</CardDescription>
      </CardHeader>
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex h-20 w-40 items-center justify-center overflow-hidden rounded-md border bg-muted">
          {url === null ? (
            <ImageIcon className="size-8 text-muted-foreground" aria-hidden="true" />
          ) : (
            <img
              src={url}
              alt={t("company.logoAlt")}
              className="max-h-full max-w-full object-contain"
            />
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <input
            ref={input}
            id="logo-file"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="sr-only"
            tabIndex={-1}
            aria-hidden="true"
            onChange={(event) => {
              onFile(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
          <Button
            variant="outline"
            disabled={upload.isPending}
            onClick={() => {
              input.current?.click();
            }}
          >
            <UploadIcon aria-hidden="true" />
            {url === null ? t("company.logoUpload") : t("company.logoReplace")}
          </Button>
          {url === null ? null : (
            <Button
              variant="ghost"
              disabled={remove.isPending}
              onClick={() => {
                remove.mutate(undefined, {
                  onSuccess: () => toast.success(t("company.logoRemoved")),
                });
              }}
            >
              <Trash2Icon aria-hidden="true" />
              {t("company.logoRemove")}
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}
