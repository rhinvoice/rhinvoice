import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";

import { useI18n } from "@/components/i18n/use-i18n";
import { ErrorSummary } from "@/components/ui/error-summary";
import { Field } from "@/components/ui/field";
import { Fieldset } from "@/components/ui/fieldset";
import { Input, Textarea } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { useSaveShortcut } from "@/components/use-key-shortcuts";
import {
  ARTICLE_FIELD_ORDER,
  articleFieldFor,
  type ArticleFormValues,
  articleSchema,
  priceCurrencies,
  SUPPLIES,
  TAX_CATEGORIES,
} from "@/features/articles/article-form-model";
import { FormAlert } from "@/features/shared/form-alert";
import { summaryItems } from "@/features/shared/form-errors";
import { FormFooter } from "@/features/shared/form-footer";
import { companyQuery } from "@/features/shared/company-api";
import { offersCategory, taxCategoryLabel } from "@/features/shared/country-profile-model";
import { unitsQuery } from "@/features/shared/reference-api";
import { applyServerErrors } from "@/features/shared/server-errors";
import { useErrorMessage } from "@/features/shared/use-error-message";

interface ArticleFormProps {
  readonly defaultValues: ArticleFormValues;
  readonly onSubmit: (values: ArticleFormValues) => Promise<unknown>;
}

export function ArticleForm({ defaultValues, onSubmit }: ArticleFormProps) {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const units = useQuery(unitsQuery);
  const company = useQuery(companyQuery).data;
  const profile = company?.profile;
  const form = useForm<ArticleFormValues>({
    resolver: zodResolver(articleSchema(t, locale)),
    mode: "onTouched",
    shouldFocusError: false,
    defaultValues,
  });
  const { errors, isSubmitted, submitCount, isSubmitting, isDirty } = form.formState;
  const error = (name: keyof ArticleFormValues) => errors[name]?.message;

  const submit = form.handleSubmit(async (values) => {
    try {
      await onSubmit(values);
      form.reset(values);
    } catch (caught) {
      if (!applyServerErrors(caught, form.setError, t, articleFieldFor)) {
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
            count: summaryItems(errors, ARTICLE_FIELD_ORDER).length,
          })}
          items={summaryItems(errors, ARTICLE_FIELD_ORDER)}
          submitCount={submitCount}
        />
      ) : null}
      <FormAlert message={errors.root?.message ?? null} />
      <Fieldset legend={t("customers.sectionBasics")}>
        <Field label={t("articles.name")} error={error("name")}>
          <Input id="name" {...form.register("name")} />
        </Field>
        <Field
          label={t("articles.description")}
          description={t("articles.descriptionHint")}
          error={error("description")}
          optionalLabel={t("common.optional")}
        >
          <Textarea id="description" rows={3} {...form.register("description")} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label={t("articles.numberLabel")}
            description={t("customers.numberHint")}
            error={error("number")}
            optionalLabel={t("common.optional")}
          >
            <Input id="number" {...form.register("number")} />
          </Field>
          <Field
            label={t("articles.group")}
            error={error("group")}
            optionalLabel={t("common.optional")}
          >
            <Input id="group" {...form.register("group")} />
          </Field>
          <Field label={t("articles.unit")} error={error("unit")}>
            <NativeSelect id="unit" {...form.register("unit")}>
              {(
                units.data ?? [
                  {
                    code: defaultValues.unit,
                    label_de: defaultValues.unit,
                    label_en: defaultValues.unit,
                  },
                ]
              ).map((unit) => (
                <option key={unit.code} value={unit.code}>
                  {locale === "en" ? unit.label_en : unit.label_de} ({unit.code})
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label={t("articles.taxCategory")} error={error("tax_category")}>
            <NativeSelect id="tax_category" {...form.register("tax_category")}>
              {TAX_CATEGORIES.filter(
                // Without a third rate in the country (e.g. Germany) it is not offered,
                // unless the article already uses it.
                (category) =>
                  offersCategory(category, profile) || category === defaultValues.tax_category,
              ).map((category) => (
                <option key={category} value={category}>
                  {taxCategoryLabel(category, profile, locale, t)}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field
            label={t("articles.supply")}
            description={t("articles.supplyHint")}
            error={error("supply")}
            className="sm:col-span-2"
          >
            <NativeSelect id="supply" {...form.register("supply")}>
              {SUPPLIES.map((supply) => (
                <option key={supply} value={supply}>
                  {t(`supply.${supply}`)}
                </option>
              ))}
            </NativeSelect>
          </Field>
        </div>
      </Fieldset>
      <Fieldset legend={t("articles.prices")} description={t("articles.pricesHint")}>
        <div className="grid gap-4 sm:grid-cols-2">
          {priceCurrencies(company?.default_currency).map((currency) => {
            const name = currency === "CHF" ? "price_chf" : "price_eur";
            return (
              <Field
                key={currency}
                label={t("articles.priceIn", { currency })}
                error={error(name)}
                optionalLabel={t("common.optional")}
              >
                <Input
                  id={name}
                  inputMode="decimal"
                  className="text-right tabular-nums"
                  {...form.register(name)}
                />
              </Field>
            );
          })}
        </div>
      </Fieldset>
      <FormFooter saving={isSubmitting} dirty={isDirty} />
    </form>
  );
}
