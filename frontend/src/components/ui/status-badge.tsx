import { cva } from "class-variance-authority";
import {
  BanIcon,
  CircleAlertIcon,
  CircleCheckIcon,
  CircleDashedIcon,
  CircleOffIcon,
  ClockIcon,
  FileCheckIcon,
  PencilLineIcon,
  SendIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
  type LucideIcon,
} from "lucide-react";

export type DocumentStatusTone =
  | "draft"
  | "sent"
  | "issued"
  | "partially_paid"
  | "paid"
  | "overdue"
  | "cancelled"
  | "accepted"
  | "declined"
  | "expired"
  | "written_off";

const badge = cva(
  "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
  {
    variants: {
      tone: {
        draft: "bg-status-draft-bg text-status-draft-fg",
        sent: "bg-status-sent-bg text-status-sent-fg",
        issued: "bg-status-issued-bg text-status-issued-fg",
        partially_paid: "bg-status-partially-paid-bg text-status-partially-paid-fg",
        paid: "bg-status-paid-bg text-status-paid-fg",
        overdue: "bg-status-overdue-bg text-status-overdue-fg",
        cancelled: "bg-status-cancelled-bg text-status-cancelled-fg",
        accepted: "bg-status-accepted-bg text-status-accepted-fg",
        declined: "bg-status-declined-bg text-status-declined-fg",
        expired: "bg-status-expired-bg text-status-expired-fg",
        // Closed without money, like a cancelled invoice: the same quiet tone, its own icon.
        written_off: "bg-status-cancelled-bg text-status-cancelled-fg",
      },
    },
  },
);

const ICONS: Readonly<Record<DocumentStatusTone, LucideIcon>> = {
  draft: PencilLineIcon,
  sent: SendIcon,
  issued: FileCheckIcon,
  partially_paid: CircleDashedIcon,
  paid: CircleCheckIcon,
  overdue: CircleAlertIcon,
  cancelled: BanIcon,
  accepted: ThumbsUpIcon,
  declined: ThumbsDownIcon,
  expired: ClockIcon,
  written_off: CircleOffIcon,
};

/** Status is shown with icon, text and colour – never colour alone (WCAG 1.4.1). */
export function StatusBadge({
  tone,
  label,
}: {
  readonly tone: DocumentStatusTone;
  readonly label: string;
}) {
  const Icon = ICONS[tone];
  return (
    <span className={badge({ tone })} data-status={tone}>
      <Icon className="size-3.5" aria-hidden="true" />
      {label}
    </span>
  );
}
