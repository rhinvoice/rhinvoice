import { useQuery } from "@tanstack/react-query";
import { ArrowUpCircleIcon, TriangleAlertIcon } from "lucide-react";
import { useEffect } from "react";

import { CopyLine } from "@/components/copy-line";
import { useI18n } from "@/components/i18n/use-i18n";
import { ExternalLink } from "@/components/external-link";
import { Button } from "@/components/ui/button";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { updatesQuery, useInstallUpdate } from "@/features/updates/api";
import {
  RESTART_POLL_MS,
  restartedInto,
  updateNotice,
  type UpdateNotice,
} from "@/features/updates/update-model";
import { cn } from "@/lib/cn";

/** Installs the update and waits for the restarted program, then loads it. */
function InstallButton({ current }: { readonly current: string }) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const install = useInstallUpdate();
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
          install.mutate();
        }}
      >
        {install.isPending ? t("updates.installing") : t("updates.install")}
      </Button>
      {install.isError ? (
        <p role="alert" className="text-xs text-destructive">
          {errorMessage(install.error) ?? t("error.generic")}
        </p>
      ) : null}
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
          <InstallButton current={current} />
        </>
      );
    case "command":
      return (
        <>
          <strong className="text-sm">
            {t("updates.newVersion", { version: notice.version })}
          </strong>
          <span>{t("updates.commandEnv")}</span>
          <CopyLine text={notice.envLine} />
          <span>{t("updates.commandRun")}</span>
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
          <Button asChild size="sm">
            <a href={notice.setupUrl} target="_blank" rel="noreferrer">
              {t("updates.setupDownload")}
            </a>
          </Button>
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
        <p>
          {(data?.checked_at ?? null) === null ? t("updates.notChecked") : t("updates.upToDate")}
        </p>
      )}
    </section>
  );
}
