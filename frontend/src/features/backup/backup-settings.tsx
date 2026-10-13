import { useQuery } from "@tanstack/react-query";
import { ExternalLinkIcon } from "lucide-react";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { backupQuery, useRequestBackup, type BackupRun } from "@/features/backup/api";
import { backupActivity } from "@/features/backup/backup-model";
import { BackupBadge, BackupSummary } from "@/features/backup/backup-status";
import { FormAlert } from "@/features/shared/form-alert";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { docsUrl } from "@/lib/about";
import { formatBytes, formatDateTime } from "@/lib/format";

export function BackupSettings() {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const query = useQuery(backupQuery);
  const request = useRequestBackup();
  const backup = query.data;
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold">{t("backup.title")}</h2>
        <p className="text-sm text-muted-foreground">{t("backup.description")}</p>
      </div>
      <FormAlert message={query.isError ? errorMessage(query.error) : null} />
      {backup === undefined ? (
        query.isPending ? (
          <Skeleton className="h-48" />
        ) : null
      ) : (
        <>
          <Card aria-labelledby="backup-state-title">
            <CardHeader className="flex-row items-center justify-between gap-2">
              <CardTitle id="backup-state-title">{t("backup.stateTitle")}</CardTitle>
              <BackupBadge state={backup.state} />
            </CardHeader>
            <BackupSummary backup={backup} />
            {backup.state === "not_set_up" ? (
              <p className="text-sm text-muted-foreground">
                {t("backup.setUpHint")}{" "}
                <a
                  href={docsUrl("operations/backup", locale)}
                  className="inline-flex items-center gap-1 text-primary underline underline-offset-4"
                  rel="noreferrer"
                  target="_blank"
                >
                  {t("backup.guide")}
                  <ExternalLinkIcon className="size-3.5" aria-hidden="true" />
                  <span className="sr-only">{t("common.opensInNewTab")}</span>
                </a>
              </p>
            ) : (
              <div className="flex flex-wrap items-center gap-3">
                <Button
                  disabled={backupActivity(backup) !== "idle" || request.isPending}
                  onClick={() => {
                    request.mutate(undefined, {
                      onSuccess: () => toast.success(t("backup.requested")),
                      onError: (caught) => toast.error(errorMessage(caught) ?? t("error.generic")),
                    });
                  }}
                >
                  {t("backup.now")}
                </Button>
                {/* Always mounted: screen readers announce changes of a live region. */}
                <p className="text-sm text-muted-foreground" role="status">
                  {
                    {
                      idle: "",
                      waiting: t("backup.pending"),
                      running: t("backup.running"),
                    }[backupActivity(backup)]
                  }
                </p>
              </div>
            )}
          </Card>
          <BackupRuns runs={backup.runs} />
          <p className="text-sm text-muted-foreground">{t("backup.retention")}</p>
        </>
      )}
    </div>
  );
}

function BackupRuns({ runs }: { readonly runs: readonly BackupRun[] }) {
  const { t, locale } = useI18n();
  const shown = runs.filter((run) => run.status !== "not_configured");
  if (shown.length === 0) {
    return null;
  }
  return (
    <Table scrollLabel={t("backup.runs")}>
      <caption className="sr-only">{t("backup.runs")}</caption>
      <TableHeader>
        <TableRow>
          <TableHead>{t("backup.startedAt")}</TableHead>
          <TableHead>{t("backup.reasonTitle")}</TableHead>
          <TableHead>{t("backup.result")}</TableHead>
          <TableHead className="text-right">{t("backup.added")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {shown.map((run) => (
          <TableRow key={run.id}>
            <TableCell className="whitespace-nowrap">
              {formatDateTime(run.started_at, locale)}
            </TableCell>
            <TableCell>{t(`backup.reason.${run.reason}`)}</TableCell>
            <TableCell className={run.status === "failed" ? "text-status-overdue-fg" : undefined}>
              {t(`backup.status.${run.status}`)}
              {run.message === null ? null : (
                <span className="block text-xs text-muted-foreground">{run.message}</span>
              )}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {run.data_added === null ? "–" : `+${formatBytes(run.data_added, locale)}`}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
