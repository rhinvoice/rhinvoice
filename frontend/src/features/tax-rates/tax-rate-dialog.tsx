import { zodResolver } from "@hookform/resolvers/zod";
import { EyeIcon, EyeOffIcon, Trash2Icon, XIcon } from "lucide-react";
import { useId, useState } from "react";
import { useForm, useWatch, type UseFormReturn } from "react-hook-form";
import { toast } from "sonner";

import { ExternalLink } from "@/components/external-link";
import { useI18n } from "@/components/i18n/use-i18n";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
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
import { NativeSelect } from "@/components/ui/native-select";
import { useRunOnce, useSubmitOnce } from "@/components/use-run-once";
import { FormAlert } from "@/features/shared/form-alert";
import { applyServerErrors } from "@/features/shared/server-errors";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { useUnsavedChanges } from "@/features/shared/use-unsaved-changes";
import {
  useDeleteTaxRate,
  useHideTaxRate,
  useSaveTaxRate,
  type RateCategory,
  type TaxRate,
} from "@/features/tax-rates/api";
import {
  currentIndex,
  emptyTaxRate,
  formToRequest,
  percentProblem,
  RATE_CATEGORIES,
  rateValueSchema,
  taxRateFieldFor,
  taxRateSchema,
  taxRateToForm,
  withValue,
  type RateValueFormValues,
  type TaxRateFormValues,
} from "@/features/tax-rates/tax-rate-form-model";
import { docsUrl } from "@/lib/about";
import { todayIso } from "@/lib/dates";
import { formatDate, formatPercent } from "@/lib/format";
import { parseDecimal } from "@/lib/format/parse-decimal";

/** The docs page that explains the categories and dated percentages. */
const DOCS_PAGE = "invoices/tax-rates";

/**
 * Add or edit a tax rate (ADR 0044, variant 2B): today's percentage in front, a change from
 * a date in a small dialog of its own, the history on demand.
 */
export function TaxRateDialog({
  rate,
  onClose,
}: {
  readonly rate: TaxRate | null;
  readonly onClose: () => void;
}) {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const save = useSaveTaxRate(rate?.id ?? null);
  const today = todayIso();
  const form = useForm<TaxRateFormValues>({
    resolver: zodResolver(taxRateSchema(t, locale)),
    mode: "onChange",
    defaultValues: rate === null ? emptyTaxRate(today) : taxRateToForm(rate, locale),
  });
  const category = useWatch({ control: form.control, name: "category" });
  const { errors, isDirty } = form.formState;
  useUnsavedChanges(isDirty);
  const error = (name: "name" | "category" | "exemption_reason" | "notice") =>
    errors[name]?.message;

  const submit = form.handleSubmit(async (values) => {
    try {
      await save.mutateAsync(formToRequest(values, locale));
      toast.success(t("taxRates.saved", { name: values.name }));
      once.finish();
      onClose();
    } catch (caught) {
      const attached = applyServerErrors(caught, form.setError, t, taxRateFieldFor);
      if (!attached) form.setError("root", { type: "server", message: errorMessage(caught) ?? "" });
    }
  });
  const once = useSubmitOnce(submit);

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent closeLabel={t("common.close")}>
        <DialogHeader>
          <DialogTitle>
            {rate === null ? t("taxRates.addTitle") : t("taxRates.editTitle")}
          </DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={once.submit} noValidate>
          <FormAlert message={errors.root?.message ?? null} />
          <Field label={t("taxRates.name")} error={error("name")}>
            <Input id="tax-rate-name" autoComplete="off" {...form.register("name")} />
          </Field>
          <div className="flex flex-col gap-1.5">
            <Field
              label={t("taxRates.categoryLabel")}
              description={rate === null ? undefined : t("taxRates.categoryFixed")}
              error={error("category")}
            >
              <NativeSelect
                id="tax-rate-category"
                disabled={rate !== null}
                {...form.register("category", {
                  // A changed category checks the percentages against it right away.
                  onChange: () => {
                    void form.trigger("values");
                  },
                })}
              >
                {RATE_CATEGORIES.map((option) => (
                  <option key={option} value={option}>
                    {t(`taxRates.category.${option}`)}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <p className="text-sm text-muted-foreground">
              {t(`taxRates.categoryHint.${category}`)}{" "}
              <ExternalLink href={docsUrl(DOCS_PAGE, locale)} className="text-primary">
                {t("taxRates.categoryDocs")}
              </ExternalLink>
            </p>
          </div>
          {category === "E" ? (
            <Field
              label={t("taxRates.exemptionReason")}
              description={t("taxRates.exemptionReasonHint")}
              error={error("exemption_reason")}
            >
              <Input
                id="tax-rate-exemption_reason"
                autoComplete="off"
                {...form.register("exemption_reason")}
              />
            </Field>
          ) : null}
          <PercentFields form={form} isNew={rate === null} today={today} />
          <Field
            label={t("taxRates.notice")}
            description={t("taxRates.noticeHint")}
            error={error("notice")}
            optionalLabel={t("common.optional")}
          >
            <Input id="tax-rate-notice" autoComplete="off" {...form.register("notice")} />
          </Field>
          <DialogFooter className="sm:items-center">
            {rate === null ? null : <RateActions rate={rate} onDeleted={onClose} />}
            <Button type="button" variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" busy={once.busy}>
              {t("common.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/**
 * The percentage in force today and its date; a new rate also asks from when it applies.
 * "Change from date …" adds a value, "Show history" lists all of them.
 */
function PercentFields({
  form,
  isNew,
  today,
}: {
  readonly form: UseFormReturn<TaxRateFormValues>;
  readonly isNew: boolean;
  readonly today: string;
}) {
  const { t, locale } = useI18n();
  const historyId = useId();
  const values = useWatch({ control: form.control, name: "values" });
  const category = useWatch({ control: form.control, name: "category" });
  const [history, setHistory] = useState(false);
  const [adding, setAdding] = useState(false);
  const errors = form.formState.errors.values;
  const shown = currentIndex(values, today);
  const current = values[shown];
  const percentError = (index: number) => errors?.[index]?.percent?.message;
  // An error on a value that is not shown opens the history, where it is.
  const hiddenError = values.some((_, index) => index !== shown && percentError(index));

  if (isNew) {
    return (
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("taxRates.percent")} error={percentError(0)}>
          <Input
            id="tax-rate-percent"
            inputMode="decimal"
            className="text-right tabular-nums"
            {...form.register("values.0.percent")}
          />
        </Field>
        <Field label={t("taxRates.validFrom")} error={errors?.[0]?.valid_from?.message}>
          <Input id="tax-rate-valid_from" type="date" {...form.register("values.0.valid_from")} />
        </Field>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1.5">
      <Field
        label={t("taxRates.percent")}
        description={
          current === undefined
            ? undefined
            : t("taxRates.validFromDate", { date: formatDate(current.valid_from, locale) })
        }
        error={percentError(shown)}
        className="sm:max-w-48"
      >
        <Input
          id="tax-rate-percent"
          inputMode="decimal"
          className="text-right tabular-nums"
          {...form.register(`values.${shown}.percent`)}
        />
      </Field>
      <div className="flex flex-wrap items-center gap-x-1 text-sm">
        <Button
          type="button"
          variant="link"
          size="sm"
          className="h-8 px-0"
          onClick={() => {
            setAdding(true);
          }}
        >
          {t("taxRates.changeFrom")}
        </Button>
        <span aria-hidden="true" className="text-muted-foreground">
          ·
        </span>
        <Button
          type="button"
          variant="link"
          size="sm"
          className="h-8 px-0"
          aria-expanded={history || hiddenError}
          aria-controls={historyId}
          onClick={() => {
            setHistory(!history);
          }}
        >
          {history || hiddenError ? t("taxRates.hideHistory") : t("taxRates.showHistory")}
        </Button>
      </div>
      {history || hiddenError ? (
        <ul
          id={historyId}
          className="flex flex-col rounded-lg border"
          aria-label={t("taxRates.history")}
        >
          {values.map((value, index) => {
            const percent = parseDecimal(value.percent, locale);
            const problem = percentError(index);
            return (
              <li
                key={value.valid_from}
                className="flex flex-wrap items-center gap-x-3 border-b px-3 py-1.5 text-sm last:border-b-0"
              >
                <span className="flex-1 tabular-nums">
                  {t("taxRates.fromDate", { date: formatDate(value.valid_from, locale) })}
                </span>
                <span className="tabular-nums">
                  {percent === null ? value.percent : formatPercent(percent, locale)}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  disabled={values.length === 1}
                  aria-label={t("taxRates.removeValue", {
                    date: formatDate(value.valid_from, locale),
                  })}
                  onClick={() => {
                    form.setValue(
                      "values",
                      values.filter((_, at) => at !== index),
                      { shouldDirty: true, shouldValidate: true },
                    );
                  }}
                >
                  <XIcon aria-hidden="true" />
                </Button>
                {problem === undefined ? null : (
                  <p className="w-full text-xs text-destructive">{problem}</p>
                )}
              </li>
            );
          })}
        </ul>
      ) : null}
      {adding ? (
        <ChangeFromDateDialog
          category={category}
          onAdd={(added) => {
            form.setValue("values", withValue(values, added), {
              shouldDirty: true,
              shouldValidate: true,
            });
            setHistory(true);
          }}
          onClose={() => {
            setAdding(false);
          }}
        />
      ) : null}
    </div>
  );
}

/** A new percentage from a date; one on the same date is replaced. */
function ChangeFromDateDialog({
  category,
  onAdd,
  onClose,
}: {
  readonly category: RateCategory;
  readonly onAdd: (value: RateValueFormValues) => void;
  readonly onClose: () => void;
}) {
  const { t, locale } = useI18n();
  const form = useForm<RateValueFormValues>({
    resolver: zodResolver(rateValueSchema(t, locale)),
    mode: "onTouched",
    defaultValues: { valid_from: "", percent: "" },
  });
  const { errors } = form.formState;
  const add = form.handleSubmit((values) => {
    const problem = percentProblem(category, values.percent, locale, t);
    if (problem !== null) {
      form.setError("percent", { type: "category", message: problem }, { shouldFocus: true });
      return;
    }
    onAdd(values);
    onClose();
  });

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent closeLabel={t("common.close")} className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{t("taxRates.changeFromTitle")}</DialogTitle>
          <DialogDescription>{t("taxRates.changeFromHint")}</DialogDescription>
        </DialogHeader>
        {/* Its own form: the rate's form around it is not submitted. */}
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.stopPropagation();
            void add(event);
          }}
          noValidate
        >
          <Field label={t("taxRates.validFrom")} error={errors.valid_from?.message}>
            <Input id="tax-rate-change-valid_from" type="date" {...form.register("valid_from")} />
          </Field>
          <Field label={t("taxRates.percent")} error={errors.percent?.message}>
            <Input
              id="tax-rate-change-percent"
              inputMode="decimal"
              className="text-right tabular-nums"
              {...form.register("percent")}
            />
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit">{t("taxRates.addValue")}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Hide or show a rate and delete one nothing uses; each acts at once. */
function RateActions({
  rate,
  onDeleted,
}: {
  readonly rate: TaxRate;
  readonly onDeleted: () => void;
}) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const hide = useHideTaxRate();
  const remove = useDeleteTaxRate();
  const once = useRunOnce();
  const [deleting, setDeleting] = useState(false);

  return (
    <div className="flex flex-col gap-2 sm:mr-auto sm:flex-row sm:items-center">
      <Button
        type="button"
        variant="ghost"
        busy={once.busy && hide.isPending}
        onClick={() =>
          once.run(() =>
            hide.mutateAsync({ id: rate.id, hidden: !rate.hidden }).then(
              () => {
                toast.success(
                  t(rate.hidden ? "taxRates.shown" : "taxRates.hidden", { name: rate.name }),
                );
              },
              (caught: unknown) => {
                toast.error(errorMessage(caught));
              },
            ),
          )
        }
      >
        {rate.hidden ? <EyeIcon aria-hidden="true" /> : <EyeOffIcon aria-hidden="true" />}
        {rate.hidden ? t("taxRates.show") : t("taxRates.hide")}
      </Button>
      {rate.in_use ? (
        <p className="text-xs text-muted-foreground sm:max-w-40">{t("taxRates.inUse")}</p>
      ) : (
        <Button
          type="button"
          variant="ghost"
          className="text-destructive hover:bg-destructive/10 hover:text-destructive"
          onClick={() => {
            setDeleting(true);
          }}
        >
          <Trash2Icon aria-hidden="true" />
          {t("common.delete")}
        </Button>
      )}
      <AlertDialog open={deleting} onOpenChange={setDeleting}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("taxRates.deleteTitle", { name: rate.name })}</AlertDialogTitle>
            <AlertDialogDescription>{t("taxRates.deleteDescription")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              destructive
              onClick={() =>
                once.run(() =>
                  remove.mutateAsync(rate.id).then(
                    () => {
                      toast.success(t("taxRates.deleted", { name: rate.name }));
                      onDeleted();
                    },
                    (caught: unknown) => {
                      toast.error(errorMessage(caught));
                    },
                  ),
                )
              }
            >
              {t("common.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
