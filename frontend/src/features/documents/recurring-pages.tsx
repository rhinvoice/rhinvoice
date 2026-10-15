import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import {
  CircleAlertIcon,
  CircleStopIcon,
  type LucideIcon,
  PauseIcon,
  PlayIcon,
  PlusIcon,
  RepeatIcon,
  Trash2Icon,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";

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
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { PageHeader } from "@/components/ui/page-header";
import { RadioCard } from "@/components/ui/radio-cards";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge, type DocumentStatusTone } from "@/components/ui/status-badge";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDocumentTitle } from "@/components/use-document-title";
import { documentQuery } from "@/features/documents/api";
import { DocumentEditor } from "@/features/documents/document-editor";
import { emptyDocument, type DocumentFormValues } from "@/features/documents/document-form-model";
import { defaultTexts } from "@/features/documents/document-texts";
import {
  planQuery,
  plansQuery,
  useDeletePlan,
  usePlanAction,
  useSavePlan,
  type Plan,
  type PlanRun,
} from "@/features/documents/recurring-api";
import {
  ACTIONS,
  INTERVALS,
  documentToPlanForm,
  emptySettings,
  planSettings,
  planState,
  planToForm,
  settingsProblems,
  toPlanRequest,
  type PlanSettings,
  type PlanState,
  type SettingsField,
  type SettingsProblem,
} from "@/features/documents/recurring-model";
import { BackLink } from "@/features/shared/back-link";
import { companyQuery, type Company } from "@/features/shared/company-api";
import { FormAlert } from "@/features/shared/form-alert";
import { mailServerQuery } from "@/features/shared/mail-api";
import { textTemplatesQuery } from "@/features/shared/texts-api";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { todayIso } from "@/lib/dates";
import { formatDate, formatMoney } from "@/lib/format";
import { errorMessageKey } from "@/lib/i18n";

const STATES: Readonly<Record<PlanState, { readonly icon: LucideIcon; readonly tone: string }>> = {
  active: { icon: PlayIcon, tone: "bg-status-paid-bg text-status-paid-fg" },
  paused: { icon: PauseIcon, tone: "bg-status-draft-bg text-status-draft-fg" },
  finished: { icon: CircleStopIcon, tone: "bg-status-expired-bg text-status-expired-fg" },
  problem: { icon: CircleAlertIcon, tone: "bg-status-overdue-bg text-status-overdue-fg" },
};

/** The state of a plan with its own icon and text, never colour alone (WCAG 1.4.1). */
function PlanStateBadge({ state }: { readonly state: PlanState }) {
  const { t } = useI18n();
  const { icon: Icon, tone } = STATES[state];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap ${tone}`}
      data-state={state}
    >
      <Icon className="size-3.5" aria-hidden="true" />
      {t(`recurring.stateLabel.${state}`)}
    </span>
  );
}

function PageSkeleton() {
  const { t } = useI18n();
  return (
    <div className="flex flex-col gap-4" aria-busy="true" aria-label={t("app.loading")}>
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-96 w-full" />
    </div>
  );
}

/** All plans: what they invoice, to whom, when next, and whether the last run went well. */
export function RecurringListPage() {
  const { t, locale } = useI18n();
  useDocumentTitle(t("app.pageTitle", { title: t("recurring.title") }));
  const errorMessage = useErrorMessage();
  const plans = useQuery(plansQuery);
  const now = new Date();
  const newButton = (
    <Button asChild>
      <Link to="/recurring/new">
        <PlusIcon aria-hidden="true" />
        {t("recurring.new")}
      </Link>
    </Button>
  );
  return (
    <>
      <BackLink to="/invoices" label={t("nav.invoices")} />
      <PageHeader
        title={t("recurring.title")}
        description={t("recurring.description")}
        actions={plans.data === undefined || plans.data.length === 0 ? null : newButton}
      />
      {plans.isError ? <FormAlert message={errorMessage(plans.error)} /> : null}
      {plans.data === undefined ? (
        plans.isPending ? (
          <Skeleton className="h-64" />
        ) : null
      ) : plans.data.length === 0 ? (
        <EmptyState
          icon={RepeatIcon}
          title={t("recurring.emptyTitle")}
          description={t("recurring.emptyDescription")}
          action={newButton}
        />
      ) : (
        <>
          {/* Phones get a list of cards, wider screens the table (principles.md 4.3). */}
          <ul className="flex flex-col gap-3 md:hidden">
            {plans.data.map((plan) => (
              <li key={plan.id}>
                <Link
                  to="/recurring/$planId"
                  params={{ planId: plan.id }}
                  className="flex flex-col gap-1 rounded-lg border bg-card p-4 hover:bg-muted"
                >
                  <span className="flex items-start justify-between gap-2">
                    <span className="font-medium">{plan.name}</span>
                    <PlanStateBadge state={planState(plan, now)} />
                  </span>
                  <span className="text-sm text-muted-foreground">{plan.customer_name}</span>
                  <span className="text-sm tabular-nums">
                    {t(`recurring.intervalOption.${plan.interval}`)}
                    {plan.finished ? "" : ` · ${formatDate(plan.next_date, locale)}`}
                    {plan.total === null
                      ? ""
                      : ` · ${formatMoney(plan.total, plan.template.currency, locale)}`}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          <div className="hidden md:block">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("recurring.name")}</TableHead>
                  <TableHead>{t("recurring.customer")}</TableHead>
                  <TableHead>{t("recurring.interval")}</TableHead>
                  <TableHead>{t("recurring.nextDate")}</TableHead>
                  <TableHead className="text-right">{t("recurring.amount")}</TableHead>
                  <TableHead>{t("recurring.action")}</TableHead>
                  <TableHead>{t("recurring.state")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {plans.data.map((plan) => {
                  const state = planState(plan, now);
                  return (
                    <TableRow key={plan.id}>
                      <TableCell>
                        <Link
                          to="/recurring/$planId"
                          params={{ planId: plan.id }}
                          className="inline-flex min-h-6 items-center font-medium text-primary underline-offset-4 hover:underline"
                        >
                          {plan.name}
                        </Link>
                      </TableCell>
                      <TableCell>{plan.customer_name}</TableCell>
                      <TableCell className="whitespace-nowrap">
                        {t(`recurring.intervalOption.${plan.interval}`)}
                      </TableCell>
                      <TableCell className="whitespace-nowrap tabular-nums">
                        {plan.finished ? "–" : formatDate(plan.next_date, locale)}
                      </TableCell>
                      <TableCell className="text-right whitespace-nowrap tabular-nums">
                        {plan.total === null
                          ? "–"
                          : formatMoney(plan.total, plan.template.currency, locale)}
                      </TableCell>
                      <TableCell>{t(`recurring.actionShort.${plan.action}`)}</TableCell>
                      <TableCell>
                        <PlanStateBadge state={state} />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </>
      )}
    </>
  );
}

function useCompanyAndTexts(): {
  readonly company: Company | null | undefined;
  readonly ready: boolean;
  readonly error: unknown;
} {
  const company = useQuery(companyQuery);
  const templates = useQuery(textTemplatesQuery);
  return {
    company: company.data,
    ready: company.data !== undefined && !templates.isPending,
    error: company.error,
  };
}

/** A new plan, empty or repeating an invoice (``fromDocument``). */
export function NewPlanPage({ fromDocument }: { readonly fromDocument?: string | undefined }) {
  const { t, locale } = useI18n();
  useDocumentTitle(t("app.pageTitle", { title: t("recurring.new") }));
  const errorMessage = useErrorMessage();
  const { company, ready, error } = useCompanyAndTexts();
  const templates = useQuery(textTemplatesQuery);
  const source = useQuery({
    ...documentQuery(fromDocument ?? ""),
    enabled: fromDocument !== undefined,
  });
  if (error !== null) return <FormAlert message={errorMessage(error)} />;
  if (!ready || company === undefined || (fromDocument !== undefined && source.isPending)) {
    return <PageSkeleton />;
  }
  if (company === null) return <FormAlert message={t("documents.companyMissing")} />;
  const defaults: DocumentFormValues =
    source.data === undefined
      ? {
          ...emptyDocument(company),
          ...defaultTexts(templates.data ?? [], "invoice", company.default_language),
        }
      : documentToPlanForm(source.data, locale);
  return (
    <PlanEditor
      notice={source.data?.treatment_overridden === true ? t("recurring.overriddenSource") : null}
      company={company}
      plan={null}
      defaults={defaults}
      settings={{ ...emptySettings(todayIso()), name: source.data?.subject ?? "" }}
    />
  );
}

export function PlanPage({ planId }: { readonly planId: string }) {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const plan = useQuery(planQuery(planId));
  const { company, ready, error } = useCompanyAndTexts();
  useDocumentTitle(
    t("app.pageTitle", { title: plan.data === undefined ? t("app.loading") : plan.data.name }),
  );
  if (plan.isError || error !== null) {
    return <FormAlert message={errorMessage(plan.error ?? error)} />;
  }
  if (plan.data === undefined || !ready || company === undefined) return <PageSkeleton />;
  if (company === null) return <FormAlert message={t("documents.companyMissing")} />;
  return (
    <PlanEditor
      key={plan.data.id}
      company={company}
      plan={plan.data}
      defaults={planToForm(plan.data, company, locale)}
      settings={planSettings(plan.data)}
    />
  );
}

interface PlanEditorProps {
  /** Something to know about the plan's starting point, shown above the editor. */
  readonly notice?: string | null | undefined;
  readonly company: Company;
  readonly plan: Plan | null;
  readonly defaults: DocumentFormValues;
  readonly settings: PlanSettings;
}

function PlanEditor({ notice, company, plan, defaults, settings: initial }: PlanEditorProps) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const save = useSavePlan(plan?.id ?? null);
  const [settings, setSettings] = useState(initial);
  const [saved, setSaved] = useState(initial);
  const [checked, setChecked] = useState(false);
  const problems = checked ? settingsProblems(settings) : new Map<SettingsField, SettingsProblem>();
  const slot = {
    problems: [...problems].map(([field, problem]) => ({
      fieldId: `plan-${field}`,
      message: `${t(`recurring.field.${field}`)}: ${t(`recurring.problem.${problem}`)}`,
    })),
    dirty: JSON.stringify(settings) !== JSON.stringify(saved),
    saveLabel: plan === null ? t("recurring.create") : t("common.save"),
    validate: () => {
      // The error summary takes the focus and links to the fields.
      setChecked(true);
      return settingsProblems(settings).size === 0;
    },
    settings: (
      <SettingsCard
        settings={settings}
        problems={problems}
        onChange={(patch) => {
          setSettings((current) => ({ ...current, ...patch }));
        }}
      />
    ),
  };
  return (
    <>
      <BackLink to="/recurring" label={t("recurring.title")} />
      <PageHeader
        title={plan === null ? t("recurring.new") : plan.name}
        description={plan === null ? t("recurring.newDescription") : plan.customer_name}
        actions={plan === null ? null : <PlanActions plan={plan} />}
      />
      {notice === null || notice === undefined ? null : (
        <p className="rounded-md bg-status-overdue-bg px-3 py-2 text-sm text-status-overdue-fg">
          {notice}
        </p>
      )}
      {plan === null ? null : <PlanStatus plan={plan} />}
      <DocumentEditor
        type="invoice"
        company={company}
        isNew={plan === null}
        defaultValues={defaults}
        plan={slot}
        onSave={(draft) => save.mutateAsync(toPlanRequest(settings, draft))}
        onSaved={async (stored) => {
          setSaved(settings);
          if (plan === null) {
            await navigate({
              to: "/recurring/$planId",
              params: { planId: stored.id },
              replace: true,
            });
          }
          toast.success(plan === null ? t("recurring.created") : t("common.saved"));
        }}
      />
    </>
  );
}

interface SettingsCardProps {
  readonly settings: PlanSettings;
  readonly problems: ReadonlyMap<SettingsField, SettingsProblem>;
  readonly onChange: (patch: Partial<PlanSettings>) => void;
}

function SettingsCard({ settings, problems, onChange }: SettingsCardProps) {
  const { t } = useI18n();
  const mail = useQuery(mailServerQuery);
  const error = (field: SettingsField): string | undefined => {
    const problem = problems.get(field);
    return problem === undefined ? undefined : t(`recurring.problem.${problem}`);
  };
  return (
    <Card aria-labelledby="plan-title">
      <CardHeader>
        <CardTitle id="plan-title" className="text-base">
          {t("recurring.planTitle")}
        </CardTitle>
        <CardDescription>{t("recurring.planDescription")}</CardDescription>
      </CardHeader>
      <div className="grid gap-4 @md:grid-cols-2">
        <Field
          className="@md:col-span-2"
          label={t("recurring.name")}
          description={t("recurring.nameHint")}
          error={error("name")}
        >
          <Input
            id="plan-name"
            value={settings.name}
            maxLength={120}
            onChange={(event) => {
              onChange({ name: event.target.value });
            }}
          />
        </Field>
        <Field label={t("recurring.interval")}>
          <NativeSelect
            id="plan-interval"
            value={settings.interval}
            onChange={(event) => {
              const next = INTERVALS.find((interval) => interval === event.target.value);
              if (next !== undefined) onChange({ interval: next });
            }}
          >
            {INTERVALS.map((interval) => (
              <option key={interval} value={interval}>
                {t(`recurring.intervalOption.${interval}`)}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field
          label={t("recurring.startDate")}
          description={t("recurring.startDateHint")}
          error={error("startDate")}
        >
          <Input
            id="plan-startDate"
            type="date"
            value={settings.startDate}
            onChange={(event) => {
              onChange({ startDate: event.target.value });
            }}
          />
        </Field>
        <Field
          label={t("recurring.endDate")}
          description={t("recurring.endDateHint")}
          error={error("endDate")}
          optionalLabel={t("common.optional")}
        >
          <Input
            id="plan-endDate"
            type="date"
            value={settings.endDate}
            onChange={(event) => {
              onChange({ endDate: event.target.value });
            }}
          />
        </Field>
      </div>
      <fieldset className="flex flex-col gap-1.5">
        <legend className="mb-1.5 text-sm font-medium">{t("recurring.onTheDay")}</legend>
        <div className="grid gap-2 @md:grid-cols-3">
          {ACTIONS.map((action) => (
            <RadioCard
              key={action}
              id={`plan-action-${action}`}
              name="plan-action"
              value={action}
              checked={settings.action === action}
              label={t(`recurring.actionOption.${action}`)}
              onChange={() => {
                onChange({ action });
              }}
            />
          ))}
        </div>
        <p className="text-sm text-muted-foreground">
          {t(`recurring.actionHint.${settings.action}`)}
        </p>
        {settings.action === "send" && mail.data?.configured === false ? (
          <p className="text-sm text-status-overdue-fg">
            {t("recurring.mailNotConfigured")}{" "}
            <Link
              to="/settings"
              search={{ tab: "mail" }}
              className="font-medium underline underline-offset-4"
            >
              {t("mail.setUp")}
            </Link>
          </p>
        ) : null}
      </fieldset>
      <div className="flex items-center gap-3">
        <Switch
          id="plan-service-period"
          checked={settings.servicePeriod}
          onCheckedChange={(servicePeriod) => {
            onChange({ servicePeriod });
          }}
        />
        <Label htmlFor="plan-service-period" className="font-normal">
          {t("recurring.servicePeriod")}
        </Label>
      </div>
    </Card>
  );
}

function PlanStatus({ plan }: { readonly plan: Plan }) {
  const { t, locale } = useI18n();
  const state = planState(plan, new Date());
  return (
    <Card aria-labelledby="plan-status-title">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <CardTitle id="plan-status-title" className="text-base">
          {t("recurring.statusTitle")}
        </CardTitle>
        <PlanStateBadge state={state} />
      </div>
      <p className="text-sm">
        {plan.finished
          ? t("recurring.finished")
          : plan.service_period
            ? t("recurring.nextWithPeriod", {
                date: formatDate(plan.next_date, locale),
                to: formatDate(plan.period_end, locale),
              })
            : t("recurring.next", { date: formatDate(plan.next_date, locale) })}
        {!plan.active && !plan.finished ? ` ${t("recurring.pausedHint")}` : ""}
      </p>
      {plan.customer_archived && plan.active && !plan.finished ? (
        <p className="text-sm text-status-overdue-fg">{t("recurring.customerArchived")}</p>
      ) : null}
      {plan.runs.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("recurring.noRuns")}</p>
      ) : (
        <ul className="flex flex-col gap-2 text-sm" aria-label={t("recurring.runs")}>
          {plan.runs.map((run) => (
            <RunItem key={run.period_start} run={run} />
          ))}
        </ul>
      )}
    </Card>
  );
}

const RUN_TONES: Readonly<Record<PlanRun["outcome"], DocumentStatusTone>> = {
  draft: "draft",
  issued: "issued",
  sent: "sent",
  failed: "overdue",
};

function RunItem({ run }: { readonly run: PlanRun }) {
  const { t, locale } = useI18n();
  const problem = runProblem(t, run);
  return (
    <li className="flex flex-col gap-1 border-b pb-2 last:border-b-0">
      <span className="flex flex-wrap items-center gap-2">
        <span className="tabular-nums">{formatDate(run.period_start, locale)}</span>
        <StatusBadge tone={RUN_TONES[run.outcome]} label={t(`recurring.outcome.${run.outcome}`)} />
        {run.document_id === null ? null : (
          <Link
            to="/documents/$documentId"
            params={{ documentId: run.document_id }}
            className="inline-flex min-h-6 items-center text-primary underline-offset-4 hover:underline"
          >
            {t("recurring.openInvoice")}
          </Link>
        )}
      </span>
      {problem === null ? null : <span className="text-status-overdue-fg">{problem}</span>}
    </li>
  );
}

function runProblem(t: ReturnType<typeof useI18n>["t"], run: PlanRun): ReactNode {
  if (run.code === "") return null;
  if (run.code === "customer_email_missing") return t("recurring.customerEmailMissing");
  if (run.code === "interrupted") {
    return run.document_id === null
      ? t("recurring.interrupted")
      : t("recurring.interruptedAfterCreate");
  }
  const key = errorMessageKey(run.code);
  return key === "error.generic" ? run.message : t(key);
}

function PlanActions({ plan }: { readonly plan: Plan }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const errorMessage = useErrorMessage();
  const pause = usePlanAction("pause");
  const resume = usePlanAction("resume");
  const remove = useDeletePlan();
  const [confirming, setConfirming] = useState(false);
  const fail = (caught: unknown) => {
    toast.error(errorMessage(caught) ?? t("error.generic"));
  };
  return (
    <div className="flex flex-wrap gap-2">
      {plan.finished ? null : plan.active ? (
        <Button
          variant="outline"
          disabled={pause.isPending}
          onClick={() => {
            pause.mutate(plan.id, {
              onSuccess: () => toast.success(t("recurring.paused")),
              onError: fail,
            });
          }}
        >
          <PauseIcon aria-hidden="true" />
          {t("recurring.pause")}
        </Button>
      ) : (
        <Button
          variant="outline"
          disabled={resume.isPending}
          onClick={() => {
            resume.mutate(plan.id, {
              onSuccess: () => toast.success(t("recurring.resumed")),
              onError: fail,
            });
          }}
        >
          <PlayIcon aria-hidden="true" />
          {t("recurring.resume")}
        </Button>
      )}
      <Button
        variant="outline"
        onClick={() => {
          setConfirming(true);
        }}
      >
        <Trash2Icon aria-hidden="true" />
        {t("recurring.delete")}
      </Button>
      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("recurring.deleteTitle", { name: plan.name })}</AlertDialogTitle>
            <AlertDialogDescription>{t("recurring.deleteDescription")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                remove.mutate(plan.id, {
                  onSuccess: () => {
                    toast.success(t("recurring.deleted", { name: plan.name }));
                    void navigate({ to: "/recurring" });
                  },
                  onError: fail,
                });
              }}
            >
              {t("recurring.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
