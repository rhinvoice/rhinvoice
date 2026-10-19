import { useQuery } from "@tanstack/react-query";
import { ArrowUpCircleIcon, TriangleAlertIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { CopyLine } from "@/components/copy-line";
import { useI18n } from "@/components/i18n/use-i18n";
import { ExternalLink } from "@/components/external-link";
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
import { useErrorMessage } from "@/features/shared/use-error-message";
import { useHasUnsavedChanges } from "@/features/shared/use-unsaved-changes";
import {
  updatesQuery,
  useCheckUpdates,
  useDownloadSetup,
  useInstallUpdate,
  useRunSetup,
} from "@/features/updates/api";
import {
  RESTART_POLL_MS,
  downloadPercent,
  megabytes,
  restartedInto,
  updateNotice,
  type SetupDownload,
  type UpdateNotice,
} from "@/features/updates/update-model";
import { cn } from "@/lib/cn";

/** How far the setup has come: a bar and "38 of 58 MB". */
function DownloadProgress({ download }: { readonly download: SetupDownload }) {
  const { t } = useI18n();
  const text = t("updates.setupDownloading", {
    received: String(megabytes(download.received)),
    total: String(megabytes(download.total)),
  });
  return (
    <div className="flex flex-col gap-1.5">
      <div
        role="progressbar"
        aria-label={text}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={downloadPercent(download)}
        className="h-1.5 overflow-hidden rounded-full bg-muted"
      >
        <div
          className="h-full rounded-full bg-primary transition-[width] duration-200 motion-reduce:transition-none"
          style={{ width: `${String(downloadPercent(download))}%` }}
        />
      </div>
      <span className="text-xs tabular-nums">{text}</span>
    </div>
  );
}

/**
 * Asks before the program closes for an update (ADR 0031): the user saves first, and is
 * told when a form on the page still holds unsaved changes.
 */
function CloseForUpdateDialog({
  open,
  onOpenChange,
  text,
  onConfirm,
  download = null,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly text: string;
  readonly onConfirm: () => void;
  /** A setup: confirming waits until it is downloaded and checked. */
  readonly download?: SetupDownload | null;
}) {
  const { t } = useI18n();
  const unsaved = useHasUnsavedChanges();
  const waiting = download !== null && download.state !== "ready";
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("updates.closeTitle")}</AlertDialogTitle>
          <AlertDialogDescription>
            {text} {t("updates.closeSaveFirst")}
          </AlertDialogDescription>
        </AlertDialogHeader>
        {unsaved ? (
          <p className="flex items-start gap-2 rounded-lg bg-status-partially-paid-bg p-3 text-sm text-status-partially-paid-fg">
            <TriangleAlertIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            {t("updates.closeUnsaved")}
          </p>
        ) : null}
        {download !== null && download.state === "downloading" ? (
          <DownloadProgress download={download} />
        ) : null}
        {download !== null && download.state === "failed" ? (
          <p role="alert" className="text-sm text-destructive">
            {t("updates.setupFailed")}
          </p>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel>{t("updates.later")}</AlertDialogCancel>
          <AlertDialogAction disabled={waiting} onClick={onConfirm}>
            {unsaved ? t("updates.closeAnyway") : t("updates.closeConfirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

/** Asks, installs the update and waits for the restarted program, then loads it. */
function InstallButton({
  current,
  version,
}: {
  readonly current: string;
  readonly version: string;
}) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const install = useInstallUpdate();
  const [asking, setAsking] = useState(false);
  const restarting = useQuery({
    ...updatesQuery,
    queryKey: ["updates", "restart"],
    enabled: install.isSuccess,
    refetchInterval: RESTART_POLL_MS,
    retry: true,
  });
  const done = restartedInto(current, restarting.data);
  useEffect(() => {
    if (done) {
      window.location.reload();
    }
  }, [done]);
  if (install.isSuccess) {
    return (
      <p role="status" className="text-xs">
        {t("updates.restarting")}
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-1.5">
      <Button
        type="button"
        size="sm"
        disabled={install.isPending}
        onClick={() => {
          setAsking(true);
        }}
      >
        {install.isPending ? t("updates.installing") : t("updates.install")}
      </Button>
      {install.isError ? (
        <p role="alert" className="text-xs text-destructive">
          {errorMessage(install.error) ?? t("error.generic")}
        </p>
      ) : null}
      <CloseForUpdateDialog
        open={asking}
        onOpenChange={setAsking}
        text={t("updates.closeRestart", { version })}
        onConfirm={() => {
          install.mutate();
        }}
      />
    </div>
  );
}

/**
 * Downloads the new setup in the program, asks, and hands over to it (ADR 0031): the
 * program closes, the setup installs and starts it again.
 */
function SetupButton({
  version,
  download,
  setupUrl,
}: {
  readonly version: string;
  readonly download: SetupDownload;
  readonly setupUrl: string;
}) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const start = useDownloadSetup();
  const run = useRunSetup();
  const [asking, setAsking] = useState(false);
  if (run.isSuccess) {
    return (
      <p role="status" className="text-xs">
        {t("updates.closing")}
      </p>
    );
  }
  const failed = download.state === "failed";
  const label =
    download.state === "ready"
      ? t("updates.setupInstall")
      : failed
        ? t("updates.setupRetry")
        : t("updates.install");
  const error = start.error ?? run.error;
  return (
    <div className="flex flex-col gap-1.5">
      {download.state === "downloading" ? <DownloadProgress download={download} /> : null}
      {download.state === "ready" ? <span>{t("updates.setupReady")}</span> : null}
      {failed ? <span>{t("updates.setupFailed")}</span> : null}
      <Button
        type="button"
        size="sm"
        disabled={start.isPending || run.isPending}
        onClick={() => {
          if (download.state === "idle" || failed) {
            start.mutate();
          }
          setAsking(true);
        }}
      >
        {label}
      </Button>
      {error === null ? null : (
        <p role="alert" className="text-xs text-destructive">
          {errorMessage(error) ?? t("error.generic")}
        </p>
      )}
      {failed ? (
        <ExternalLink href={setupUrl} className="inline-flex min-h-6 items-center self-start">
          {t("updates.setupByHand")}
        </ExternalLink>
      ) : null}
      <CloseForUpdateDialog
        open={asking}
        onOpenChange={setAsking}
        text={t("updates.closeSetup", { version })}
        download={download}
        onConfirm={() => {
          run.mutate();
        }}
      />
    </div>
  );
}

function Notes({ url }: { readonly url: string | null }) {
  const { t } = useI18n();
  return url === null ? null : (
    // At least 24 px high: a target of its own, not a link within a sentence (WCAG 2.5.8).
    <ExternalLink href={url} className="inline-flex min-h-6 items-center self-start text-primary">
      {t("updates.notes")}
    </ExternalLink>
  );
}

/** What to do about a newer release: install it, the command, the setup, or a failure. */
export function UpdateNoticeContent({
  notice,
  current,
}: {
  readonly notice: UpdateNotice;
  readonly current: string;
}) {
  const { t } = useI18n();
  switch (notice.kind) {
    case "install":
      return (
        <>
          <strong className="text-sm">
            {t("updates.newVersion", { version: notice.version })}
          </strong>
          <span>{t("updates.installHint")}</span>
          <Notes url={notice.notesUrl} />
          <InstallButton current={current} version={notice.version} />
        </>
      );
    case "command":
      return (
        <>
          <strong className="text-sm">
            {t("updates.newVersion", { version: notice.version })}
          </strong>
          {notice.envLine === null ? (
            <span>{t("updates.commandOnly")}</span>
          ) : (
            <>
              <span>
                {t(notice.pinned === true ? "updates.commandEnv" : "updates.commandEnvIfPinned")}
              </span>
              <CopyLine text={notice.envLine} />
              <span>{t("updates.commandRun")}</span>
            </>
          )}
          <CopyLine text={notice.command} />
          <Notes url={notice.notesUrl} />
        </>
      );
    case "setup":
      return (
        <>
          <strong className="text-sm">
            {t("updates.setupTitle", { version: notice.version })}
          </strong>
          <span>{t("updates.setupHint")}</span>
          <Notes url={notice.notesUrl} />
          {notice.download === null ? (
            <Button asChild size="sm">
              <a href={notice.setupUrl} target="_blank" rel="noreferrer">
                {t("updates.setupDownload")}
              </a>
            </Button>
          ) : (
            <SetupButton
              version={notice.version}
              download={notice.download}
              setupUrl={notice.setupUrl}
            />
          )}
        </>
      );
    case "failed":
      return (
        <>
          <strong className="text-sm">
            {t("updates.failedTitle", { version: notice.version })}
          </strong>
          <span>{t("updates.failedHint", { current: notice.current })}</span>
        </>
      );
  }
}

/** Variant B: a quiet card at the foot of the navigation, only when there is news. */
export function UpdateCard() {
  const { t } = useI18n();
  const { data } = useQuery(updatesQuery);
  const notice = updateNotice(data);
  if (notice === null || data === undefined) {
    return null;
  }
  const attention = notice.kind === "setup" || notice.kind === "failed";
  const Icon = attention ? TriangleAlertIcon : ArrowUpCircleIcon;
  return (
    <section
      aria-label={t("updates.title")}
      className={cn(
        "mx-1 mb-1 flex flex-col gap-2 rounded-lg border bg-card p-3 text-xs text-muted-foreground",
        attention && "border-transparent bg-status-partially-paid-bg text-status-partially-paid-fg",
      )}
    >
      <Icon aria-hidden="true" className="size-4 text-current" />
      <UpdateNoticeContent notice={notice} current={data.current} />
    </section>
  );
}

/** Asks for the newest release now; the section above shows the answer. */
function CheckButton() {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const check = useCheckUpdates();
  return (
    <div className="flex flex-col gap-1.5">
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="self-start"
        disabled={check.isPending}
        onClick={() => {
          check.mutate();
        }}
      >
        {check.isPending ? t("updates.checking") : t("updates.check")}
      </Button>
      {check.isError ? (
        <p role="alert" className="text-xs text-destructive">
          {errorMessage(check.error) ?? t("error.generic")}
        </p>
      ) : null}
    </div>
  );
}

/** The same in "About Rhinvoice", plus whether this is the newest version. */
export function UpdateSection() {
  const { t } = useI18n();
  const { data } = useQuery(updatesQuery);
  const notice = updateNotice(data);
  return (
    <section
      aria-label={t("updates.title")}
      className="flex flex-col gap-2 border-t pt-4 text-sm text-muted-foreground"
    >
      {notice !== null && data !== undefined ? (
        <UpdateNoticeContent notice={notice} current={data.current} />
      ) : (
        <p role="status">
          {(data?.checked_at ?? null) === null ? t("updates.notChecked") : t("updates.upToDate")}
        </p>
      )}
      {data?.can_check === true && notice?.kind !== "install" ? <CheckButton /> : null}
    </section>
  );
}
