import type { DocumentDetail } from "@/features/documents/api";

export const WRITE_OFF_REASONS = [
  "gone",
  "time_barred",
  "small_amount",
  "untraceable",
  "other",
] as const;

export type WriteOffReason = (typeof WRITE_OFF_REASONS)[number];

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** 31 December of the invoice's year, at the latest today. */
export function endOfInvoiceYear(issueDate: string, today: string): string {
  const end = `${issueDate.slice(0, 4)}-12-31`;
  return end < today ? end : today;
}

/** A write-off is dated from the invoice date up to today (the server checks the same). */
export function isWriteOffDate(value: string, issueDate: string | null, today: string): boolean {
  return ISO_DATE.test(value) && value <= today && (issueDate === null || value >= issueDate);
}

type Writable = Pick<DocumentDetail, "type" | "status">;

/** Open invoices can be written off, also imported ones: nothing is built from their lines. */
export function canWriteOff(document: Writable): boolean {
  return (
    document.type === "invoice" &&
    (document.status === "issued" || document.status === "partially_paid")
  );
}

/** What a payment may amount to: the open rest, or what was written off of it. */
export function paymentLimit(
  document: Pick<DocumentDetail, "status" | "open_amount" | "written_off_amount">,
): string {
  return document.status === "written_off" ? document.written_off_amount : document.open_amount;
}

export interface WriteOffEvent {
  readonly amount: string;
  readonly date: string;
  readonly reason: WriteOffReason;
}

const EVENT = /^\d+\.\d{2} \d{4}-\d{2}-\d{2} \w+$/;
const DATE_LENGTH = "2021-12-31".length;

/** The detail of a "written_off" event: "<amount> <date> <reason>". */
export function parseWriteOffEvent(detail: string): WriteOffEvent | null {
  if (!EVENT.test(detail)) return null;
  const dateStart = detail.indexOf(" ") + 1;
  const name = detail.slice(dateStart + DATE_LENGTH + 1);
  const reason = WRITE_OFF_REASONS.find((candidate) => candidate === name);
  if (reason === undefined) return null;
  return {
    amount: detail.slice(0, dateStart - 1),
    date: detail.slice(dateStart, dateStart + DATE_LENGTH),
    reason,
  };
}
