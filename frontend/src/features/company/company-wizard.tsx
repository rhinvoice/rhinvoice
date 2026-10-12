import { zodResolver } from "@hookform/resolvers/zod";
import { CheckIcon } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type RefObject } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ErrorSummary } from "@/components/ui/error-summary";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useDocumentTitle } from "@/components/use-document-title";
import { useSaveCompany } from "@/features/company/api";
import {
  COMPANY_FIELD_ORDER,
  companyFieldFor,
  companySchema,
  emptyCompany,
  formToRequest,
  type CompanyFormValues,
} from "@/features/company/company-form-model";
import { AddressFields } from "@/features/shared/address-fields";
import {
  countrySummary,
  termsFor,
  type CountryProfile,
} from "@/features/shared/country-profile-model";
import { FormAlert } from "@/features/shared/form-alert";
import { summaryItems } from "@/features/shared/form-errors";
import { applyServerErrors } from "@/features/shared/server-errors";
import { countryProfilesQuery } from "@/features/shared/reference-api";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { cn } from "@/lib/cn";
import { countryName } from "@/lib/countries";

type CompanyCountry = CountryProfile["country"];

interface CompanyWizardProps {
  /** The company was saved. */
  readonly onDone: () => void;
  /** "Set up later": the dashboard's checklist keeps the step. */
  readonly onLater: () => void;
}

/**
 * First start: the country, then the company. Everything else (bank account,
 * numbers, customers) follows as a checklist on the dashboard.
 */
export function CompanyWizard({ onDone, onLater }: CompanyWizardProps) {
  const { t } = useI18n();
  useDocumentTitle(t("app.pageTitle", { title: t("wizard.title") }));
  const profiles = useQuery(countryProfilesQuery);
  const [step, setStep] = useState<"country" | "company">("country");
  const [country, setCountry] = useState<CompanyCountry>("CH");
  const [smallBusiness, setSmallBusiness] = useState(false);
  /** What was typed in the company step, kept when going back to the country. */
  const [entered, setEntered] = useState<CompanyFormValues | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const firstRender = useRef(true);
  // The button that changed the step is gone: focus moves to the new step's heading.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    heading.current?.focus();
  }, [step]);
  const steps = [
    ["country", t("wizard.stepCountry")],
    ["company", t("wizard.stepCompany")],
  ] as const;
  return (
    <main id="main" className="flex min-h-dvh justify-center px-4 py-10">
      <div className="flex w-full max-w-2xl flex-col gap-6">
        <div className="flex items-center gap-2">
          <img src="/favicon.svg" alt="" className="size-8" />
          <p className="text-lg font-semibold tracking-tight">{t("wizard.title")}</p>
        </div>
        <ol className="flex flex-wrap gap-2" aria-label={t("wizard.steps")}>
          {steps.map(([key, label], index) => {
            const current = key === step;
            const done = key === "country" && step === "company";
            return (
              <li
                key={key}
                aria-current={current ? "step" : undefined}
                className={cn(
                  "flex items-center gap-2 rounded-full px-3 py-1 text-sm",
                  current
                    ? "bg-accent font-medium text-accent-foreground"
                    : "text-muted-foreground",
                )}
              >
                <span
                  className={cn(
                    "flex size-6 items-center justify-center rounded-full border text-xs",
                    current && "border-primary",
                  )}
                  aria-hidden="true"
                >
                  {done ? <CheckIcon className="size-3.5" /> : index + 1}
                </span>
                {label}
                {done ? <span className="sr-only">{t("wizard.stepDone")}</span> : null}
              </li>
            );
          })}
        </ol>
        {profiles.isError || profiles.data?.length === 0 ? (
          <Card role="alert" className="flex flex-col gap-4">
            <p className="text-sm">{t("error.generic")}</p>
            <div className="flex flex-wrap justify-between gap-2">
              <Button type="button" variant="ghost" onClick={onLater}>
                {t("wizard.later")}
              </Button>
              <Button type="button" onClick={() => void profiles.refetch()}>
                {t("error.retry")}
              </Button>
            </div>
          </Card>
        ) : profiles.data === undefined ? (
          <p role="status" className="text-sm text-muted-foreground">
            {t("app.loading")}
          </p>
        ) : step === "country" ? (
          <CountryStep
            heading={heading}
            profiles={profiles.data}
            country={country}
            smallBusiness={smallBusiness}
            onCountry={setCountry}
            onSmallBusiness={setSmallBusiness}
            onNext={() => {
              setStep("company");
            }}
            onLater={onLater}
          />
        ) : (
          <CompanyStep
            heading={heading}
            profile={profileOf(profiles.data, country)}
            smallBusiness={smallBusiness}
            entered={entered}
            onBack={(values) => {
              setEntered(values);
              setStep("country");
            }}
            onDone={onDone}
          />
        )}
      </div>
    </main>
  );
}

function profileOf(profiles: readonly CountryProfile[], country: CompanyCountry): CountryProfile {
  const profile = profiles.find((candidate) => candidate.country === country) ?? profiles[0];
  if (profile === undefined) throw new Error("no country profiles");
  return profile;
}

interface CountryStepProps {
  readonly heading: RefObject<HTMLHeadingElement | null>;
  readonly profiles: readonly CountryProfile[];
  readonly country: CompanyCountry;
  readonly smallBusiness: boolean;
  readonly onCountry: (country: CompanyCountry) => void;
  readonly onSmallBusiness: (value: boolean) => void;
  readonly onNext: () => void;
  readonly onLater: () => void;
}

function CountryStep({
  heading,
  profiles,
  country,
  smallBusiness,
  onCountry,
  onSmallBusiness,
  onNext,
  onLater,
}: CountryStepProps) {
  const { t, locale } = useI18n();
  return (
    <Card>
      <form
        className="flex flex-col gap-6"
        onSubmit={(event) => {
          event.preventDefault();
          onNext();
        }}
      >
        <div className="flex flex-col gap-1">
          <h1 ref={heading} tabIndex={-1} className="text-xl font-semibold outline-none">
            {t("wizard.countryTitle")}
          </h1>
          <p className="text-sm text-muted-foreground">{t("wizard.countryHint")}</p>
        </div>
        <fieldset className="flex flex-col gap-2">
          <legend className="sr-only">{t("wizard.stepCountry")}</legend>
          <div className="grid gap-3 sm:grid-cols-2">
            {profiles.map(({ country: code }) => (
              <label
                key={code}
                className="grid cursor-pointer grid-cols-[auto_1fr] items-start gap-x-3 gap-y-0.5 rounded-xl border border-border bg-card p-4 has-[:checked]:border-primary has-[:checked]:bg-accent has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2"
              >
                <input
                  type="radio"
                  name="country"
                  value={code}
                  checked={country === code}
                  className="mt-1 size-4 accent-primary focus-visible:ring-0"
                  onChange={() => {
                    onCountry(code);
                  }}
                />
                <span className="font-medium">{countryName(code, locale)}</span>
                <span className="col-start-2 text-sm text-muted-foreground">
                  {countrySummary(profileOf(profiles, code), locale, t)}
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        <label className="grid cursor-pointer grid-cols-[auto_1fr] items-start gap-x-3 gap-y-0.5">
          <input
            type="checkbox"
            checked={smallBusiness}
            className="mt-1 size-4 accent-primary"
            onChange={(event) => {
              onSmallBusiness(event.target.checked);
            }}
          />
          <span className="font-medium">
            {termsFor(profileOf(profiles, country), locale).small_business}
          </span>
          <span className="col-start-2 text-sm text-muted-foreground">
            {t("wizard.smallBusinessHint")}
          </span>
        </label>
        <div className="flex flex-wrap justify-between gap-2">
          <Button type="button" variant="ghost" onClick={onLater}>
            {t("wizard.later")}
          </Button>
          <Button type="submit">{t("wizard.next")}</Button>
        </div>
        <p className="text-sm text-muted-foreground">{t("wizard.changeLater")}</p>
      </form>
    </Card>
  );
}

function emptyCompanyKeeping(
  entered: CompanyFormValues | null,
  profile: CountryProfile,
): CompanyFormValues {
  const empty = emptyCompany(profile.country, profile.default_currency);
  return entered === null
    ? empty
    : {
        ...entered,
        country: profile.country,
        default_currency: empty.default_currency,
        cash_rounding: empty.cash_rounding,
      };
}

interface CompanyStepProps {
  readonly heading: RefObject<HTMLHeadingElement | null>;
  readonly profile: CountryProfile;
  readonly smallBusiness: boolean;
  readonly entered: CompanyFormValues | null;
  readonly onBack: (values: CompanyFormValues) => void;
  readonly onDone: () => void;
}

function CompanyStep({
  heading,
  profile,
  smallBusiness,
  entered,
  onBack,
  onDone,
}: CompanyStepProps) {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const save = useSaveCompany();
  const terms = termsFor(profile, locale);
  const form = useForm<CompanyFormValues>({
    resolver: zodResolver(companySchema(t, locale)),
    mode: "onTouched",
    shouldFocusError: false,
    // The country (with its currency and rounding) and the small business scheme come
    // from the first step; what was typed before stays.
    defaultValues: {
      ...entered,
      ...emptyCompanyKeeping(entered, profile),
      small_business: smallBusiness,
    },
  });
  const { errors, isSubmitted, submitCount, isSubmitting } = form.formState;
  const error = (name: keyof CompanyFormValues) => errors[name]?.message;
  const submit = form.handleSubmit(async (values) => {
    try {
      await save.mutateAsync(formToRequest(values));
      toast.success(t("wizard.saved"));
      onDone();
    } catch (caught) {
      if (!applyServerErrors(caught, form.setError, t, companyFieldFor)) {
        form.setError("root", { type: "server", message: errorMessage(caught) ?? "" });
      }
    }
  });
  return (
    <Card>
      <form className="flex flex-col gap-6" onSubmit={(event) => void submit(event)} noValidate>
        <div className="flex flex-col gap-1">
          <h1 ref={heading} tabIndex={-1} className="text-xl font-semibold outline-none">
            {t("wizard.companyTitle")}
          </h1>
          <p className="text-sm text-muted-foreground">{t("wizard.companyHint")}</p>
        </div>
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
          countries={[profile.country]}
        />
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
        </div>
        <Field
          label={terms.vat_number_field}
          description={terms.vat_number_hint}
          error={error("vat_number")}
          optionalLabel={t("common.optional")}
        >
          <Input id="vat_number" {...form.register("vat_number")} />
        </Field>
        {profile.tax_number ? (
          <Field
            label={t("company.taxNumber")}
            description={t("wizard.taxNumberHint")}
            error={error("tax_number")}
            optionalLabel={t("common.optional")}
          >
            <Input id="tax_number" {...form.register("tax_number")} />
          </Field>
        ) : null}
        <div className="flex flex-wrap justify-between gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              onBack(form.getValues());
            }}
          >
            {t("wizard.back")}
          </Button>
          <Button type="submit" disabled={isSubmitting}>
            {t("wizard.finish")}
          </Button>
        </div>
      </form>
    </Card>
  );
}
