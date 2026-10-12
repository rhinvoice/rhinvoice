import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { useI18n } from "@/components/i18n/use-i18n";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { backupQuery } from "@/features/backup/api";
import { BackupBadge, BackupSummary } from "@/features/backup/backup-status";

/** Backup state on the dashboard; warns when backups are missing or older than 24 hours. */
export function BackupCard() {
  const { t } = useI18n();
  const query = useQuery(backupQuery);
  const backup = query.data;
  if (backup === undefined) {
    // A failing request must not hide the warning: say that the state is unknown.
    return query.isError ? (
      <Card aria-labelledby="backup-title">
        <CardTitle id="backup-title">{t("backup.title")}</CardTitle>
        <p className="text-sm text-status-overdue-fg">{t("backup.unknown")}</p>
      </Card>
    ) : null;
  }
  return (
    <Card
      aria-labelledby="backup-title"
      className={backup.state === "current" ? undefined : "border-status-overdue-fg/40"}
    >
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle id="backup-title">{t("backup.title")}</CardTitle>
        <BackupBadge state={backup.state} />
      </CardHeader>
      <BackupSummary backup={backup} />
      <Link
        to="/settings"
        search={{ tab: "backup" }}
        className="flex min-h-6 w-full items-center text-sm text-primary underline-offset-4 hover:underline"
      >
        {backup.state === "current" ? t("backup.show") : t("backup.check")}
      </Link>
    </Card>
  );
}
