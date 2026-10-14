import { useQuery } from "@tanstack/react-query";
import { ExternalLinkIcon } from "lucide-react";
import { useState } from "react";
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
import {
  backupQuery,
  backupSetupQuery,
  useRequestBackup,
  type Backup,
  type BackupRun,
  type BackupSetup,
} from "@/features/backup/api";
import { backupActivity, canBackUpNow, setupStep } from "@/features/backup/backup-model";
import { FolderChooser, RecoveryKey } from "@/features/backup/backup-setup";
import { BackupBadge, BackupSummary } from "@/features/backup/backup-status";
import { FormAlert } from "@/features/shared/form-alert";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { docsUrl } from "@/lib/about";
import { formatBytes, formatDateTime } from "@/lib/format";

/** What the installation without Docker shows below the state, on request. */
type Shown = "nothing" | "key" | "folder";

export function BackupSettings() {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const query = useQuery(backupQuery);
  // Answers 409 in the Docker setup: there the backup container is set up instead.
  const setupQuery = useQuery(backupSetupQuery);
  const [shown, setShown] = useState<Shown>("nothing");
  const backup = query.data;
  const setup = setupQuery.data;
  const step = setup === undefined ? null : setupStep(setup);
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold">{t("backup.title")}</h2>
        <p className="text-sm text-muted-foreground">{t("backup.description")}</p>
      </div>
      <FormAlert message={query.isError ? errorMessage(query.error) : null} />
      {backup === undefined || setupQuery.isPending ? (
        query.isPending || setupQuery.isPending ? (
          <Skeleton className="h-48" />
        ) : null
      ) : setup !== undefined && step === "choose" ? (
        <FolderChooser setup={setup} />
      ) : (
        <>
          {step === "key" ? <RecoveryKey mustConfirm /> : null}
          <BackupState
            backup={backup}
            setup={setup}
            onShowKey={() => {
              setShown(shown === "key" ? "nothing" : "key");
            }}
            onChangeFolder={() => {
              setShown("folder");
            }}
          />
          {setup !== undefined && step === "ready" && shown === "key" ? (
            <RecoveryKey
              mustConfirm={false}
              onHide={() => {
                setShown("nothing");
              }}
            />
          ) : null}
          {setup !== undefined && shown === "folder" ? (
            <FolderChooser
              setup={setup}
              onDone={() => {
                setShown("nothing");
                toast.success(t("backup.setup.changed"));
              }}
              onCancel={() => {
                setShown("nothing");
              }}
            />
          ) : null}
          <BackupRuns runs={backup.runs} />
          <p className="text-sm text-muted-foreground">{t("backup.retention")}</p>
        </>
      )}
    </div>
  );
}

function BackupState({
  backup,
  setup,
  onShowKey,
  onChangeFolder,
}: {
  readonly backup: Backup;
  /** Only in the installation without Docker. */
  readonly setup: BackupSetup | undefined;
  readonly onShowKey: () => void;
  readonly onChangeFolder: () => void;
}) {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const request = useRequestBackup();
  const activity = backupActivity(backup);
  const folder = setup?.folder ?? null;
  return (
    <Card aria-labelledby="backup-state-title">
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle id="backup-state-title">{t("backup.stateTitle")}</CardTitle>
        <BackupBadge state={backup.state} />
      </CardHeader>
      <BackupSummary backup={backup} />
      {folder === null ? null : (
        <p className="text-sm break-all text-muted-foreground">{t("backup.folder", { folder })}</p>
      )}
      {setup === undefined && backup.state === "not_set_up" ? (
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
          {canBackUpNow(backup) ? (
            <Button
              disabled={activity !== "idle" || request.isPending}
              onClick={() => {
                request.mutate(undefined, {
                  onSuccess: () => toast.success(t("backup.requested")),
                  onError: (caught) => toast.error(errorMessage(caught) ?? t("error.generic")),
                });
              }}
            >
              {t("backup.now")}
            </Button>
          ) : (
            <p className="w-full text-sm text-muted-foreground">{t("backup.firstBackup")}</p>
          )}
          {setup?.key_confirmed === true ? (
            <>
              <Button variant="outline" onClick={onShowKey}>
                {t("backup.key.show")}
              </Button>
              <Button variant="outline" onClick={onChangeFolder}>
                {t("backup.changeFolder")}
              </Button>
            </>
          ) : null}
          {/* Always mounted: screen readers announce changes of a live region. */}
          <p className="text-sm text-muted-foreground" role="status">
            {
              {
                idle: "",
                waiting: t("backup.pending"),
                running: t("backup.running"),
              }[activity]
            }
          </p>
        </div>
      )}
    </Card>
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
