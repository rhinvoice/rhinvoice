import { useI18n } from "@/components/i18n/use-i18n";
import { StatusBadge } from "@/components/ui/status-badge";
import { daysBetween, todayIso } from "@/lib/dates";

export type DisplayStatus =
  | "draft"
  | "sent"
  | "accepted"
  | "declined"
  | "expired"
  | "issued"
  | "partially_paid"
  | "overdue"
  | "paid"
  | "cancelled";

/** Status with icon and text; overdue documents also show the days (principles.md 4.6). */
export function DocumentStatusBadge({
  status,
  dueDate,
}: {
  readonly status: DisplayStatus;
  readonly dueDate?: string | null;
}) {
  const { t } = useI18n();
  const label =
    status === "overdue" && dueDate !== null && dueDate !== undefined
      ? t("status.overdueDays", { count: daysBetween(dueDate, todayIso()) })
      : t(`status.${status}`);
  return <StatusBadge tone={status} label={label} />;
}
