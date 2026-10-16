import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { Link, useBlocker } from "@tanstack/react-router";
import {
  ChevronDownIcon,
  EyeIcon,
  FileCheckIcon,
  InfoIcon,
  PencilIcon,
  PrinterIcon,
  SlidersHorizontalIcon,
  TextIcon,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode, type SyntheticEvent } from "react";
import { Controller, FormProvider, useForm, useFormContext, useWatch } from "react-hook-form";

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
import { Card, CardTitle } from "@/components/ui/card";
import { ErrorSummary, type ErrorSummaryItem } from "@/components/ui/error-summary";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { RadioCard } from "@/components/ui/radio-cards";
import { useDebouncedValue } from "@/components/use-debounced-value";
import { useSaveShortcut } from "@/components/use-key-shortcuts";
import {
  customerOptionQuery,
  previewQuery,
  renderQuery,
  type CreateRequest,
  type CustomerOption,
  type DocumentDetail,
  type DraftRequest,
  type TaxTreatment,
} from "@/features/documents/api";
import { CustomerPicker } from "@/features/documents/customer-picker";
import {
  customerDefaults,
  documentFieldFor,
  documentSchema,
  documentSummaryItems,
  fieldId,
  customerVatHint,
  formToDraft,
  goodsHintKey,
  hasSupply,
  TREATMENTS,
  type DocumentFormValues,
} from "@/features/documents/document-form-model";
import { DocumentTextFields } from "@/features/documents/document-text-fields";
import { switchLanguage } from "@/features/documents/document-texts";
import { EInvoiceProblems } from "@/features/documents/e-invoice-card";
import { LineItems } from "@/features/documents/line-items";
import { PaperPreview } from "@/components/paper-preview";
import { printPage } from "@/features/documents/print-page";
import type { Company } from "@/features/shared/company-api";
import { FormAlert } from "@/features/shared/form-alert";
import { applyServerErrors } from "@/features/shared/server-errors";
import { textTemplatesQuery } from "@/features/shared/texts-api";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { cn } from "@/lib/cn";
import { addDays, todayIso } from "@/lib/dates";
import { formatMoney, formatRelative } from "@/lib/format";
import { modifierLabel } from "@/lib/shortcuts";
import { referenceHint, xrechnungOnly } from "@/lib/xrechnung";
import { termsFor } from "@/features/shared/country-profile-model";

export type EditableType = "invoice" | "quote";

const AUTOSAVE_DELAY_MS = 400;
const RELATIVE_TICK_MS = 10_000;

/** The current time, refreshed every ``interval`` ms (null: not refreshed). */
function useNow(interval: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (interval === null) return;
    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, interval);
    return () => {
      window.clearInterval(timer);
    };
  }, [interval]);
  return now;
}

/** Quick choices for the payment term, in days after the document date. */
const TERMS = [0, 10, 30, 60] as const;

/** What the editor needs to edit a recurring plan's invoice instead of a document. */
export interface PlanSlot {
  /** The plan's own settings, shown above the customer. */
  readonly settings: ReactNode;
  /** Check the plan's settings on saving; false keeps the form from being sent. */
  readonly validate: () => boolean;
  readonly saveLabel: string;
  /** What is wrong with the settings, for the error summary (empty until checked). */
  readonly problems: readonly ErrorSummaryItem[];
  /** The settings changed since the last save (leaving then asks first, like the form). */
  readonly dirty: boolean;
}

interface DocumentEditorProps<Saved> {
  readonly type: EditableType;
  readonly company: Company;
  readonly defaultValues: DocumentFormValues;
  /** Existing drafts keep their customer defaults; new ones follow the chosen customer. */
  readonly isNew: boolean;
  /** Save valid changes automatically shortly after typing (existing drafts). */
  readonly autosave?: boolean;
  readonly onSave: (draft: DraftRequest) => Promise<Saved>;
  /**
   * Runs after a successful save, once the form is clean again (so navigating
   * away is not blocked); ``issue`` is true when the user chose to issue.
   */
  readonly onSaved: (saved: Saved, issue: boolean) => Promise<unknown>;
  /** Edit the invoice of a recurring plan: no dates, no issuing, no autosave. */
  readonly plan?: PlanSlot | undefined;
}

/**
 * Editor variant A (chosen 2026-10-11): customer, dates and lines are open, texts
 * and further details are folded away; the right side shows the document as paper.
 */
export function DocumentEditor<Saved = DocumentDetail>({
  type,
  company,
  defaultValues,
  isNew,
  autosave = false,
  onSave,
  onSaved,
  plan,
}: DocumentEditorProps<Saved>) {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const schema = useMemo(() => documentSchema(t, locale), [t, locale]);
  const form = useForm<DocumentFormValues>({
    resolver: zodResolver(schema),
    mode: "onTouched",
    shouldFocusError: false,
    defaultValues,
  });
  const { errors, isSubmitted, submitCount, isSubmitting, isDirty } = form.formState;
  const [confirmIssue, setConfirmIssue] = useState(false);
  const [editing, setEditing] = useState<number | null>(() =>
    defaultValues.lines.length === 1 && defaultValues.lines[0]?.description === "" ? 0 : null,
  );
  const [pane, setPane] = useState<"form" | "preview">("form");
  const [choosingCustomer, setChoosingCustomer] = useState(false);
  const templates = useQuery(textTemplatesQuery).data ?? [];
  const values = useWatch({ control: form.control }) as DocumentFormValues;
  const tax = termsFor(company.profile, locale).tax_name;

  // Live totals and page: the last valid state of the form, from the server.
  // Debounced as a string: equal content must not count as a change.
  const parsed = schema.safeParse(values);
  const request = parsed.success
    ? JSON.stringify({ type, ...formToDraft(parsed.data, locale) } satisfies CreateRequest)
    : null;
  const debounced = useDebouncedValue(request, 400);
  const body = debounced === null ? null : (JSON.parse(debounced) as CreateRequest);
  const preview = useQuery(previewQuery(body));
  const goodsHint = goodsHintKey(preview.data?.goods_treatment, values.lines);
  const vatHint =
    preview.data?.customer_vat_missing === true && values.customer_id !== ""
      ? customerVatHint(
          values.lines,
          company.profile.vat_system,
          preview.data.treatment,
          preview.data.goods_treatment,
        )
      : null;
  const eInvoiceProblems = preview.data?.e_invoice_problems ?? [];
  // German customers only: what the XRechnung lacks beyond the e-invoice in the PDF.
  const xrechnungProblems = xrechnungOnly(preview.data?.xrechnung_problems ?? [], eInvoiceProblems);
  const page = useQuery(renderQuery(body));
  const amounts = preview.data?.line_amounts ?? [];

  // Leaving with unsaved changes asks first (also on reload or closing the tab).
  // formState is only refreshed on the next render, so a navigation right after
  // saving (e.g. to the new draft's page) must not see the old "dirty" state.
  const justSaved = useRef(false);
  const unsaved = () => (form.formState.isDirty || plan?.dirty === true) && !justSaved.current;
  useBlocker({
    shouldBlockFn: () => unsaved() && !window.confirm(t("documents.leaveConfirm")),
    enableBeforeUnload: unsaved,
  });

  // The autosave in flight, if any: a manual save waits for it, so the older
  // content can never arrive at the server after the newer one.
  const autosaving = useRef<Promise<unknown> | null>(null);

  const submit = (intent: "save" | "issue") => (event?: SyntheticEvent) => {
    // The plan's settings are checked together with the form, so all errors show at once.
    const planValid = plan === undefined || plan.validate();
    return form.handleSubmit(async (submitted) => {
      if (!planValid) return;
      try {
        await autosaving.current?.catch(() => undefined);
        const saved = await onSave(formToDraft(submitted, locale));
        form.reset(submitted);
        justSaved.current = true;
        try {
          await onSaved(saved, intent === "issue");
        } finally {
          justSaved.current = false;
        }
      } catch (caught) {
        if (!applyServerErrors(caught, form.setError, t, documentFieldFor)) {
          form.setError("root", { type: "server", message: errorMessage(caught) ?? "" });
        }
      }
    })(event);
  };
  useSaveShortcut(() => void submit("save")());

  // Existing drafts save themselves once the form has been valid and unchanged
  // for a moment (principles.md 4.4). Edits made while saving stay unsaved.
  const [autosaved, setAutosaved] = useState<{
    readonly status: "idle" | "saving" | "saved" | "failed";
    readonly at: number | null;
  }>({ status: "idle", at: null });
  useEffect(() => {
    if (!autosave || !isDirty || isSubmitting || request === null || debounced !== request) return;
    const timer = window.setTimeout(() => {
      if (autosaving.current !== null) return;
      const snapshot = structuredClone(form.getValues());
      const checked = schema.safeParse(snapshot);
      if (!checked.success) return;
      setAutosaved((current) => ({ ...current, status: "saving" }));
      autosaving.current = onSave(formToDraft(checked.data, locale))
        .then(
          () => {
            form.reset(snapshot, { keepValues: true });
            setAutosaved({ status: "saved", at: Date.now() });
          },
          () => {
            setAutosaved((current) => ({ ...current, status: "failed" }));
          },
        )
        .finally(() => {
          autosaving.current = null;
        });
    }, AUTOSAVE_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [autosave, isDirty, isSubmitting, request, debounced, form, schema, onSave, locale]);
  const now = useNow(autosaved.at === null ? null : RELATIVE_TICK_MS);

  const chooseCustomer = (customer: CustomerOption) => {
    if (!isNew) return;
    const defaults = customerDefaults(customer, company, locale);
    const texts = switchLanguage(
      form.getValues(),
      templates,
      type,
      form.getValues("language"),
      defaults.language,
    );
    const options = { shouldDirty: true } as const;
    form.setValue("currency", defaults.currency, options);
    form.setValue("language", defaults.language, options);
    form.setValue("discount_value", defaults.discount_value, options);
    form.setValue("intro_text", texts.intro_text, options);
    form.setValue("payment_text", texts.payment_text, options);
    form.setValue("closing_text", texts.closing_text, options);
  };

  const summary = [...(plan?.problems ?? []), ...documentSummaryItems(errors, t)];
  const issueLabel = type === "quote" ? t("documents.send") : t("documents.issue");
  const title = type === "quote" ? t("documentType.quote") : t("documentType.invoice");

  return (
    <FormProvider {...form}>
      <form
        className="flex flex-col gap-6"
        onSubmit={(event) => void submit("save")(event)}
        noValidate
      >
        {isSubmitted ? (
          <ErrorSummary
            title={t("validation.summary", { count: summary.length })}
            items={summary}
            submitCount={submitCount}
          />
        ) : null}
        <FormAlert message={errors.root?.message ?? null} />

        {/* Phones and narrow windows switch between editing and the paper. */}
        <div
          role="group"
          aria-label={t("documents.paneSwitch")}
          className="inline-flex w-fit gap-0.5 rounded-lg bg-muted p-1 xl:hidden"
        >
          {(["form", "preview"] as const).map((value) => (
            <Button
              key={value}
              type="button"
              size="sm"
              variant="ghost"
              aria-pressed={pane === value}
              className={cn(pane === value && "bg-card shadow-xs hover:bg-card")}
              onClick={() => {
                setPane(value);
              }}
            >
              {value === "form" ? (
                <PencilIcon aria-hidden="true" />
              ) : (
                <EyeIcon aria-hidden="true" />
              )}
              {value === "form" ? t("documents.editPane") : t("documents.previewPane")}
            </Button>
          ))}
        </div>

        <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
          <div
            className={cn(
              "@container flex min-w-0 flex-col gap-6",
              pane === "preview" && "hidden xl:flex",
            )}
          >
            {plan?.settings}
            <Card aria-labelledby="customer-title">
              <div className="flex items-center justify-between gap-2">
                <CardTitle id="customer-title" className="text-base">
                  {t("documents.customer")}
                </CardTitle>
                {values.customer_id === "" || choosingCustomer ? null : (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setChoosingCustomer(true);
                      requestAnimationFrame(() => {
                        document.getElementById(fieldId("customer_id"))?.focus();
                      });
                    }}
                  >
                    {t("documents.changeCustomer")}
                  </Button>
                )}
              </div>
              {values.customer_id === "" || choosingCustomer || errors.customer_id !== undefined ? (
                <Controller
                  control={form.control}
                  name="customer_id"
                  render={({ field }) => (
                    <Field
                      label={t("documents.customerSearch")}
                      error={errors.customer_id?.message}
                    >
                      <CustomerPicker
                        id={fieldId("customer_id")}
                        value={field.value}
                        onChange={(customer) => {
                          chooseCustomer(customer);
                          field.onChange(customer.id);
                          setChoosingCustomer(false);
                        }}
                      />
                    </Field>
                  )}
                />
              ) : (
                <CustomerCard customerId={values.customer_id} />
              )}
              <div aria-live="polite" className="flex flex-col gap-3 empty:hidden">
                {vatHint === null ? null : (
                  <p
                    className={cn(
                      "flex items-start gap-2 rounded-md px-3 py-2 text-sm",
                      // EU countries charge domestic VAT without the number; CH/LI only
                      // miss the notice.
                      company.profile.vat_system === "eu"
                        ? "bg-status-overdue-bg text-status-overdue-fg"
                        : "bg-accent text-accent-foreground",
                    )}
                  >
                    <InfoIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                    <span>
                      {t("documents.customerVatMissing", {
                        withNumber: t(`treatment.${vatHint.withNumber}`),
                        treatment: t(`treatment.${vatHint.without}`),
                      })}{" "}
                      <Link
                        to="/customers/$customerId"
                        params={{ customerId: values.customer_id }}
                        className="font-medium underline underline-offset-4"
                      >
                        {t("documents.addCustomerVat")}
                      </Link>
                    </span>
                  </p>
                )}
                {preview.data?.treatment === "reverse_charge" &&
                hasSupply(values.lines, "service") ? (
                  <p className="flex items-start gap-2 rounded-md bg-accent px-3 py-2 text-sm text-accent-foreground">
                    <InfoIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                    {t("documents.reverseChargeHint", { tax })}
                  </p>
                ) : null}
                {goodsHint === null ? null : (
                  <p className="flex items-start gap-2 rounded-md bg-accent px-3 py-2 text-sm text-accent-foreground">
                    <InfoIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                    {t(goodsHint)}
                  </p>
                )}
              </div>
            </Card>

            {plan === undefined ? (
              <Card aria-labelledby="dates-title">
                <CardTitle id="dates-title" className="text-base">
                  {t("documents.sectionDates")}
                </CardTitle>
                <div className="grid gap-4 @md:grid-cols-2">
                  <Field
                    label={t("documents.issueDate")}
                    description={t("documents.issueDateHint")}
                    error={errors.issue_date?.message}
                    optionalLabel={t("common.optional")}
                  >
                    <Input
                      id={fieldId("issue_date")}
                      type="date"
                      {...form.register("issue_date")}
                    />
                  </Field>
                  <div className="flex flex-col gap-2">
                    <Field
                      label={type === "quote" ? t("documents.validUntil") : t("documents.dueDate")}
                      description={
                        type === "quote"
                          ? t("documents.validUntilHint")
                          : t("documents.dueDateHint")
                      }
                      error={errors.due_date?.message}
                      optionalLabel={t("common.optional")}
                    >
                      <Input id={fieldId("due_date")} type="date" {...form.register("due_date")} />
                    </Field>
                    {type === "invoice" ? (
                      <div
                        role="group"
                        aria-label={t("documents.payWithin")}
                        className="flex flex-wrap gap-1.5"
                      >
                        {TERMS.map((days) => {
                          const start = values.issue_date === "" ? todayIso() : values.issue_date;
                          const due = addDays(start, days);
                          return (
                            <Button
                              key={days}
                              type="button"
                              size="sm"
                              variant="outline"
                              className="rounded-full"
                              aria-pressed={values.due_date === due}
                              onClick={() => {
                                form.setValue("due_date", due, {
                                  shouldDirty: true,
                                  shouldValidate: true,
                                });
                              }}
                            >
                              {days === 0
                                ? t("documents.dueNow")
                                : t("documents.dueInDays", { days })}
                            </Button>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>
                </div>
              </Card>
            ) : null}

            <Card aria-labelledby="lines-title">
              <div className="flex items-baseline justify-between gap-2">
                <CardTitle id="lines-title" className="text-base">
                  {t("documents.sectionLines")}
                </CardTitle>
                {preview.data === undefined ? null : (
                  <p className="text-sm text-muted-foreground tabular-nums">
                    {t("documents.netTotal", {
                      amount: formatMoney(
                        preview.data.totals.net,
                        preview.data.totals.currency,
                        locale,
                      ),
                    })}
                  </p>
                )}
              </div>
              <LineItems
                amounts={amounts}
                rates={preview.data?.rates}
                profile={company.profile}
                goodsTreatment={
                  preview.data?.goods_treatment === preview.data?.treatment
                    ? null
                    : preview.data?.goods_treatment
                }
                editing={editing}
                onEditingChange={setEditing}
              />
            </Card>

            <Card className="gap-0 py-2 md:py-2">
              <Fold
                icon={<TextIcon aria-hidden="true" />}
                title={t("documents.sectionTexts")}
                hint={t("documents.sectionTextsHint")}
                forceOpen={
                  errors.intro_text !== undefined ||
                  errors.payment_text !== undefined ||
                  errors.closing_text !== undefined
                }
              >
                <DocumentTextFields type={type} notice={preview.data?.notice} />
              </Fold>
              <Fold
                icon={<SlidersHorizontalIcon aria-hidden="true" />}
                title={t("documents.sectionMore")}
                hint={plan === undefined ? t("documents.sectionMoreHint") : t("recurring.moreHint")}
                forceOpen={
                  errors.subject !== undefined ||
                  errors.reference !== undefined ||
                  errors.service_from !== undefined ||
                  errors.service_to !== undefined ||
                  errors.discount_value !== undefined ||
                  errors.override_reason !== undefined
                }
              >
                <MoreFields
                  tax={tax}
                  autoTreatment={preview.data?.treatment}
                  plan={plan !== undefined}
                />
              </Fold>
            </Card>
          </div>

          {/* On wide screens the paper keeps its first page in view; further pages
              (e.g. the Swiss payment part) scroll inside the pane. */}
          <aside
            aria-label={t("documents.previewPane")}
            // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- a scrolling region must be reachable by keyboard (WCAG 2.1.1, axe scrollable-region-focusable)
            tabIndex={0}
            className={cn(
              "min-w-0 rounded-md xl:sticky xl:top-[calc(var(--topbar-height)+1.5rem)] xl:max-h-[calc(100dvh-var(--topbar-height)-7rem)] xl:overflow-y-auto xl:overscroll-contain",
              pane === "form" && "hidden xl:block",
            )}
          >
            <PaperPreview
              html={page.data}
              title={t("documents.previewTitle", { title })}
              busy={page.isFetching}
              placeholder={
                body === null && page.data === undefined ? t("documents.previewEmpty") : undefined
              }
              onLineClick={(index) => {
                setEditing(index);
                setPane("form");
                requestAnimationFrame(() => {
                  document.getElementById(fieldId(`lines.${String(index)}.description`))?.focus();
                });
              }}
            />
          </aside>
        </div>

        {/* Like FormFooter: sticky on larger screens, at the end of the form on phones. */}
        <div className="z-10 -mx-4 flex flex-wrap items-center justify-end gap-3 border-t bg-background/95 px-4 py-3 backdrop-blur md:sticky md:bottom-0 md:-mx-8 md:px-8">
          <p
            className={cn(
              "mr-auto text-sm",
              autosaved.status === "failed" ? "text-destructive" : "text-muted-foreground",
            )}
          >
            {/* Only changes of the state are announced, not the ticking time. */}
            <span aria-live="polite">
              {isSubmitting || autosaved.status === "saving"
                ? t("common.saving")
                : autosaved.status === "failed"
                  ? t("documents.autosaveFailed")
                  : isDirty
                    ? t("common.unsavedChanges")
                    : autosaved.at === null
                      ? ""
                      : t("common.saved")}
            </span>
            {!isDirty && autosaved.status === "saved" && autosaved.at !== null ? (
              <span aria-hidden="true">
                {" "}
                {/* The clock ticks slowly: never show a time in the future. */}
                {formatRelative(
                  new Date(autosaved.at),
                  new Date(Math.max(now, autosaved.at)),
                  locale,
                )}
              </span>
            ) : null}
          </p>
          {preview.data === undefined ? null : (
            // The total stays in view while editing long documents.
            <p className="text-right text-sm leading-tight">
              <span className="block text-xs text-muted-foreground">{t("documents.total")}</span>
              <span className="text-lg font-semibold tabular-nums">
                {formatMoney(preview.data.totals.total, preview.data.totals.currency, locale)}
              </span>
            </p>
          )}
          <Button
            type="button"
            variant="ghost"
            disabled={page.data === undefined}
            onClick={() => {
              if (page.data !== undefined) printPage(page.data);
            }}
          >
            <PrinterIcon aria-hidden="true" />
            {t("documents.print")}
          </Button>
          <Button
            type="submit"
            variant={plan === undefined ? "outline" : "default"}
            disabled={isSubmitting}
          >
            {plan?.saveLabel ?? t("common.save")}
            <span className="sr-only">{` (${modifierLabel(navigator.platform)} Enter)`}</span>
          </Button>
          {plan === undefined ? (
            <Button
              type="button"
              disabled={isSubmitting}
              onClick={() => {
                setConfirmIssue(true);
              }}
            >
              <FileCheckIcon aria-hidden="true" />
              {issueLabel}
            </Button>
          ) : null}
        </div>
      </form>

      <AlertDialog open={confirmIssue} onOpenChange={setConfirmIssue}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {type === "quote" ? t("documents.sendTitle") : t("documents.issueTitle")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {type === "quote" ? t("documents.sendDescription") : t("documents.issueDescription")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {eInvoiceProblems.length > 0 ? (
            <div className="rounded-md border border-warning/40 bg-warning/10 p-3 text-sm">
              <EInvoiceProblems label={t("eInvoice.issueWarning")} problems={eInvoiceProblems} />
            </div>
          ) : null}
          {xrechnungProblems.length > 0 ? (
            <div className="rounded-md border border-warning/40 bg-warning/10 p-3 text-sm">
              <EInvoiceProblems
                label={t("eInvoice.issueXRechnungWarning")}
                problems={xrechnungProblems}
              />
            </div>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                void submit("issue")();
              }}
            >
              {issueLabel}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </FormProvider>
  );
}

/** The chosen customer as it will be addressed. */
function CustomerCard({ customerId }: { readonly customerId: string }) {
  const { t } = useI18n();
  const customer = useQuery({ ...customerOptionQuery(customerId), enabled: customerId !== "" });
  const data = customer.data;
  if (customerId === "" || data === undefined) return null;
  const address = data.address;
  const initials = data.display_name
    .split(/\s+/)
    .map((word) => word.charAt(0))
    .slice(0, 2)
    .join("");
  return (
    <div className="flex items-start gap-3 rounded-lg bg-muted/60 p-3">
      <span
        aria-hidden="true"
        className="grid size-10 shrink-0 place-items-center rounded-full bg-accent text-sm font-semibold text-accent-foreground"
      >
        {initials}
      </span>
      <div className="flex min-w-0 flex-col text-sm">
        <span className="font-medium">{data.display_name}</span>
        <span className="text-muted-foreground">
          {[
            `${address.street} ${address.house_number}`.trim(),
            `${address.postal_code} ${address.city}`,
          ]
            .filter((part) => part !== "")
            .join(", ")}
          {` · ${address.country}`}
        </span>
        <span className="text-muted-foreground">
          {t("documents.customerNumber", { number: data.number })}
          {data.vat_number === null ? "" : ` · ${data.vat_number}`}
        </span>
      </div>
    </div>
  );
}

interface FoldProps {
  readonly icon: ReactNode;
  readonly title: string;
  readonly hint: string;
  /** Opens the section, e.g. when it contains an error. */
  readonly forceOpen: boolean;
  readonly children: ReactNode;
}

/** A section that is closed by default, so the editor stays calm. */
function Fold({ icon, title, hint, forceOpen, children }: FoldProps) {
  const [open, setOpen] = useState(false);
  const shown = open || forceOpen;
  return (
    <details
      open={shown}
      className="group border-b last:border-b-0"
      onToggle={(event) => {
        setOpen(event.currentTarget.open);
      }}
    >
      <summary className="flex min-h-12 cursor-pointer list-none items-center gap-3 py-3 [&_svg]:size-4 [&::-webkit-details-marker]:hidden">
        <span className="text-muted-foreground">{icon}</span>
        <span className="flex min-w-0 flex-col @md:flex-row @md:items-baseline @md:gap-2">
          <span className="font-semibold">{title}</span>
          <span className="truncate text-sm text-muted-foreground">{hint}</span>
        </span>
        <ChevronDownIcon
          className="ml-auto text-muted-foreground transition-transform group-open:rotate-180"
          aria-hidden="true"
        />
      </summary>
      <div className="pb-5">{children}</div>
    </details>
  );
}

interface MoreFieldsProps {
  readonly tax: string;
  /** A recurring plan: the plan fills the service period, the treatment is automatic. */
  readonly plan: boolean;
  /** The treatment the server determined, shown on the "automatic" option. */
  readonly autoTreatment: TaxTreatment | undefined;
}

/** Subject, reference, service period, currency, language, prices, discount, tax treatment. */
function MoreFields({ tax, autoTreatment, plan }: MoreFieldsProps) {
  const { t } = useI18n();
  const { register, formState, control } = useFormContext<DocumentFormValues>();
  const errors = formState.errors;
  const treatment = useWatch({ control, name: "treatment" });
  const discountKind = useWatch({ control, name: "discount_kind" });
  const currency = useWatch({ control, name: "currency" });
  const customerId = useWatch({ control, name: "customer_id" });
  const customer = useQuery({ ...customerOptionQuery(customerId), enabled: customerId !== "" });
  const hint = referenceHint(customerId === "" ? undefined : customer.data);
  return (
    <div className="grid gap-4 @md:grid-cols-2">
      <Field
        className="@md:col-span-2"
        label={t("documents.subject")}
        description={t("documents.subjectHint")}
        error={errors.subject?.message}
        optionalLabel={t("common.optional")}
      >
        <Input id={fieldId("subject")} {...register("subject")} />
      </Field>
      <Field
        label={t("documents.reference")}
        description={t(hint.key, { value: hint.value })}
        error={errors.reference?.message}
        optionalLabel={t("common.optional")}
      >
        <Input id={fieldId("reference")} {...register("reference")} />
      </Field>
      <div className="grid grid-cols-2 gap-4">
        <Field label={t("documents.currency")} error={errors.currency?.message}>
          <NativeSelect id={fieldId("currency")} {...register("currency")}>
            <option value="CHF">CHF</option>
            <option value="EUR">EUR</option>
          </NativeSelect>
        </Field>
        <Field label={t("documents.language")} error={errors.language?.message}>
          <NativeSelect id={fieldId("language")} {...register("language")}>
            <option value="de">{t("language.de")}</option>
            <option value="en">{t("language.en")}</option>
          </NativeSelect>
        </Field>
      </div>
      {plan ? null : (
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
            description={t("documents.serviceHint")}
            error={errors.service_to?.message}
            optionalLabel={t("common.optional")}
          >
            <Input id={fieldId("service_to")} type="date" {...register("service_to")} />
          </Field>
        </>
      )}
      <fieldset className="flex flex-col gap-1.5 @md:col-span-2">
        <legend className="mb-1.5 text-sm font-medium">{t("documents.priceMode")}</legend>
        <div className="grid grid-cols-2 gap-2 @md:max-w-md">
          <RadioCard
            id="price_mode-net"
            value="net"
            label={t("documents.priceModeNet", { tax })}
            {...register("price_mode")}
          />
          <RadioCard
            id="price_mode-gross"
            value="gross"
            label={t("documents.priceModeGross", { tax })}
            {...register("price_mode")}
          />
        </div>
      </fieldset>
      <Field label={t("documents.discountKind")}>
        <NativeSelect id={fieldId("discount_kind")} {...register("discount_kind")}>
          <option value="percent">{t("documents.discountPercent")}</option>
          <option value="amount">{t("documents.discountAmount", { currency })}</option>
        </NativeSelect>
      </Field>
      <Field
        label={
          discountKind === "percent"
            ? t("documents.discountValuePercent")
            : t("documents.discountValueAmount", { currency })
        }
        error={errors.discount_value?.message}
        optionalLabel={t("common.optional")}
      >
        <Input
          id={fieldId("discount_value")}
          inputMode="decimal"
          className="text-right tabular-nums"
          {...register("discount_value")}
        />
      </Field>
      {plan ? null : (
        <>
          <Field
            label={t("documents.treatment")}
            description={t("documents.treatmentHint")}
            error={errors.treatment?.message}
          >
            <NativeSelect id={fieldId("treatment")} {...register("treatment")}>
              <option value="">
                {autoTreatment === undefined || treatment !== ""
                  ? t("documents.treatmentAuto")
                  : t("documents.treatmentAutoWith", {
                      treatment: t(`treatment.${autoTreatment}`),
                    })}
              </option>
              {TREATMENTS.map((option) => (
                <option key={option} value={option}>
                  {t(`treatment.${option}`)}
                </option>
              ))}
            </NativeSelect>
          </Field>
          {treatment === "" ? null : (
            <Field
              label={t("documents.overrideReason")}
              description={t("documents.overrideReasonHint")}
              error={errors.override_reason?.message}
            >
              <Input id={fieldId("override_reason")} {...register("override_reason")} />
            </Field>
          )}
        </>
      )}
    </div>
  );
}
