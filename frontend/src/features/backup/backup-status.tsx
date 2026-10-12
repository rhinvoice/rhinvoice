import { useI18n } from "@/components/i18n/use-i18n";
import { StatusBadge, type DocumentStatusTone } from "@/components/ui/status-badge";
import type { Backup } from "@/features/backup/api";
import { lastFailure } from "@/features/backup/backup-model";
import { formatRelative } from "@/lib/format";

const TONES: Readonly<Record<Backup["state"], DocumentStatusTone>> = {
  current: "paid",
  stale: "overdue",
  not_set_up: "overdue",
};

export function BackupBadge({ state }: { readonly state: Backup["state"] }) {
  const { t } = useI18n();
  return <StatusBadge tone={TONES[state]} label={t(`backup.state.${state}`)} />;
}

/** One sentence on the state: when the last backup was made, or why there is none. */
export function BackupSummary({ backup }: { readonly backup: Backup }) {
  const { t, locale } = useI18n();
  if (backup.state === "not_set_up") {
    return <p className="text-sm">{t("backup.notSetUp")}</p>;
  }
  const finished = backup.last_success?.finished_at ?? null;
  const when = finished === null ? null : formatRelative(new Date(finished), new Date(), locale);
  const failure = lastFailure(backup);
  return (
    <div className="flex flex-col gap-1 text-sm">
      <p>{when === null ? t("backup.never") : t("backup.lastSuccess", { when })}</p>
      {failure === null ? null : (
        <p className="text-status-overdue-fg">{t("backup.lastFailure", { message: failure })}</p>
      )}
    </div>
  );
}
