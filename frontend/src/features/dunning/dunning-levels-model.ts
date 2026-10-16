import type { DunningLevel, DunningLevelRequest } from "@/features/dunning/api";

/** A level as typed: numbers stay text until they are checked. */
export interface LevelInput {
  readonly level: number;
  readonly days_after_due: string;
  readonly payment_days: string;
  readonly fee: string;
  readonly text_de: string;
  readonly text_en: string;
  readonly text_fr: string;
  readonly text_it: string;
}

/** The text fields of a level, one per document language. */
export const TEXT_FIELDS = ["text_de", "text_en", "text_fr", "text_it"] as const;
export type TextField = (typeof TEXT_FIELDS)[number];
export type LevelField = "days_after_due" | "payment_days" | "fee" | TextField;
export type LevelProblem = "days" | "paymentDays" | "fee" | "text";

const MAX_DAYS = 365;
const MAX_FEE = 1000;
const MAX_TEXT = 2000;
/** Fees fit the Swiss 5-centime rounding of the payment codes (in hundredths). */
const FEE_STEP_CENTS = 5;

export function toInput(level: DunningLevel): LevelInput {
  return {
    ...level,
    days_after_due: String(level.days_after_due),
    payment_days: String(level.payment_days),
  };
}

function wholeDays(text: string, min: number): number | null {
  const value = text.trim();
  if (!/^\d{1,3}$/.test(value)) return null;
  const days = Number(value);
  return days >= min && days <= MAX_DAYS ? days : null;
}

/** The fee in hundredths, or null when it is no valid fee ("12,50" is fine). */
function feeCents(text: string): number | null {
  const match = /^(\d{1,4})(?:[.,](\d{1,2}))?$/.exec(text.trim());
  if (match === null) return null;
  const cents = Number(match[1]) * 100 + Number((match[2] ?? "0").padEnd(2, "0"));
  return cents <= MAX_FEE * 100 && cents % FEE_STEP_CENTS === 0 ? cents : null;
}

/** Problems per field, keyed "index.field". */
export function levelProblems(levels: readonly LevelInput[]): Map<string, LevelProblem> {
  const problems = new Map<string, LevelProblem>();
  levels.forEach((level, index) => {
    if (wholeDays(level.days_after_due, 0) === null) {
      problems.set(`${String(index)}.days_after_due`, "days");
    }
    if (wholeDays(level.payment_days, 1) === null) {
      problems.set(`${String(index)}.payment_days`, "paymentDays");
    }
    if (feeCents(level.fee) === null) problems.set(`${String(index)}.fee`, "fee");
    for (const field of TEXT_FIELDS) {
      if (level[field].length > MAX_TEXT) problems.set(`${String(index)}.${field}`, "text");
    }
  });
  return problems;
}

/** The request of checked levels (see levelProblems). */
export function toRequest(level: LevelInput): DunningLevelRequest {
  const cents = feeCents(level.fee) ?? 0;
  return {
    ...level,
    days_after_due: Number(level.days_after_due.trim()),
    payment_days: Number(level.payment_days.trim()),
    fee: (cents / 100).toFixed(2),
  };
}
