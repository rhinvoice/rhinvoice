import type { DocumentDetail, DraftRequest } from "@/features/documents/api";
import {
  documentToForm,
  emptyDocument,
  lineToForm,
  newLineKey,
  type DocumentFormValues,
} from "@/features/documents/document-form-model";
import type { Interval, Plan, PlanAction, PlanRequest } from "@/features/documents/recurring-api";
import type { Company } from "@/features/shared/company-api";
import { formatDecimalInput } from "@/lib/format";
import type { Locale } from "@/lib/locale";

export const INTERVALS = [
  "monthly",
  "quarterly",
  "half_yearly",
  "yearly",
] as const satisfies readonly Interval[];
export const ACTIONS = ["draft", "issue", "send"] as const satisfies readonly PlanAction[];

/** The plan's own settings; its invoice is edited with the document form. */
export interface PlanSettings {
  readonly name: string;
  readonly interval: Interval;
  readonly startDate: string;
  readonly endDate: string;
  readonly action: PlanAction;
  readonly servicePeriod: boolean;
}

export type SettingsField = "name" | "startDate" | "endDate";
export type SettingsProblem = "required" | "endBeforeStart";

export function emptySettings(today: string): PlanSettings {
  return {
    name: "",
    interval: "monthly",
    startDate: today,
    endDate: "",
    action: "issue",
    servicePeriod: true,
  };
}

export function planSettings(plan: Plan): PlanSettings {
  return {
    name: plan.name,
    interval: plan.interval,
    startDate: plan.start_date,
    endDate: plan.end_date ?? "",
    action: plan.action,
    servicePeriod: plan.service_period,
  };
}

export function settingsProblems(settings: PlanSettings): Map<SettingsField, SettingsProblem> {
  const found = new Map<SettingsField, SettingsProblem>();
  if (settings.name.trim() === "") found.set("name", "required");
  if (settings.startDate === "") found.set("startDate", "required");
  else if (settings.endDate !== "" && settings.endDate < settings.startDate) {
    found.set("endDate", "endBeforeStart");
  }
  return found;
}

/** The plan's invoice in the document form (the plan knows no dates or tax choice). */
export function planToForm(plan: Plan, company: Company, locale: Locale): DocumentFormValues {
  const template = plan.template;
  return {
    ...emptyDocument(company),
    customer_id: plan.customer_id,
    currency: template.currency,
    language: template.language ?? company.default_language,
    price_mode: template.price_mode,
    subject: template.subject,
    reference: template.reference,
    intro_text: template.intro_text,
    payment_text: template.payment_text,
    closing_text: template.closing_text,
    bank_account_id: template.bank_account_id ?? "",
    discount_kind: template.discount_kind,
    discount_value:
      template.discount_value === null || Number(template.discount_value) === 0
        ? ""
        : formatDecimalInput(template.discount_value, locale, 0),
    lines: template.lines.map((line) => lineToForm(line, newLineKey(), locale)),
  };
}

/** A plan that repeats an invoice: its content, without its dates and tax choice. */
export function documentToPlanForm(document: DocumentDetail, locale: Locale): DocumentFormValues {
  return {
    ...documentToForm(document, locale),
    issue_date: "",
    due_date: "",
    service_from: "",
    service_to: "",
    treatment: "",
    override_reason: "",
    lines: document.lines.map((line) => lineToForm(line, newLineKey(), locale)),
  };
}

/** The plan as the API takes it: its settings and the invoice the editor sends. */
export function toPlanRequest(settings: PlanSettings, draft: DraftRequest): PlanRequest {
  return {
    name: settings.name.trim(),
    customer_id: draft.customer_id,
    interval: settings.interval,
    start_date: settings.startDate,
    end_date: settings.endDate === "" ? null : settings.endDate,
    action: settings.action,
    service_period: settings.servicePeriod,
    template: {
      // The editor always names the currency and language of the invoice.
      currency: draft.currency ?? "CHF",
      language: draft.language ?? null,
      price_mode: draft.price_mode,
      lines: draft.lines ?? [],
      discount_kind: draft.discount_kind,
      discount_value: draft.discount_value ?? null,
      subject: draft.subject,
      reference: draft.reference,
      intro_text: draft.intro_text,
      payment_text: draft.payment_text,
      closing_text: draft.closing_text,
      bank_account_id: draft.bank_account_id ?? null,
    },
  };
}

export type PlanState = "active" | "paused" | "finished" | "problem";

/** How long a run may take before an unfinished one counts as interrupted. */
export const RUN_GRACE_MS = 15 * 60 * 1000;

/** How a plan stands: a problem of its last invoice shows until the next one goes well. */
export function planState(plan: Pick<Plan, "active" | "finished" | "runs">, now: Date): PlanState {
  if (plan.finished) return "finished";
  if (!plan.active) return "paused";
  const last = plan.runs[0];
  if (last === undefined || last.code === "") return "active";
  // A run being written right now is no problem yet.
  const running =
    last.code === "interrupted" && now.getTime() - new Date(last.at).getTime() < RUN_GRACE_MS;
  return running ? "active" : "problem";
}
