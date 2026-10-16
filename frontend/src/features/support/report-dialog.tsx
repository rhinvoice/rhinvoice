import { useQuery } from "@tanstack/react-query";
import { CheckIcon, CopyIcon } from "lucide-react";
import { useState } from "react";

import { CopyLine } from "@/components/copy-line";
import { ExternalLink } from "@/components/external-link";
import { useI18n } from "@/components/i18n/use-i18n";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { supportReportQuery } from "@/features/support/api";
import {
  SERVER_LOG_COMMAND,
  SUPPORT_EMAIL,
  issueUrl,
  reportText,
  type SupportReport,
} from "@/features/support/report-model";

type Copy = "idle" | "copied" | "failed";

/** Step 1 in the program for Windows and Mac: the report goes to the clipboard. */
function CopyReport({ report }: { readonly report: SupportReport }) {
  const { t } = useI18n();
  const [copy, setCopy] = useState<Copy>("idle");
  const text = reportText(report);
  return (
    <div className="flex flex-col gap-2">
      <p>{t("support.copyStep")}</p>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="self-start"
        onClick={() => {
          // Written at once, within the click: Safari's web view refuses it later.
          navigator.clipboard.writeText(text).then(
            () => {
              setCopy("copied");
            },
            () => {
              setCopy("failed");
            },
          );
        }}
      >
        {copy === "copied" ? <CheckIcon aria-hidden="true" /> : <CopyIcon aria-hidden="true" />}
        {copy === "copied" ? t("support.copied") : t("support.copy")}
      </Button>
      {copy === "failed" ? (
        <>
          <p role="alert" className="text-xs text-destructive">
            {t("support.copyFailed")}
          </p>
          <textarea
            readOnly
            aria-label={t("support.copy")}
            value={text}
            rows={6}
            className="w-full rounded-md border bg-background p-2 font-mono text-xs"
            onFocus={(event) => {
              event.currentTarget.select();
            }}
          />
        </>
      ) : null}
    </div>
  );
}

/** Step 1 on a server: the log is read where Docker keeps it. */
function ServerLog() {
  const { t } = useI18n();
  return (
    <div className="flex flex-col gap-2">
      <p>{t("support.serverStep")}</p>
      <CopyLine text={SERVER_LOG_COMMAND} />
    </div>
  );
}

/** How to report a problem: copy the report, then send it. Nothing is sent by itself. */
export function ReportDialog({
  open,
  onOpenChange,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}) {
  const { t } = useI18n();
  // Asked when the window opens, so that the copy happens within the click.
  const report = useQuery({ ...supportReportQuery, enabled: open }).data;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("common.close")}>
        <DialogHeader>
          <DialogTitle>{t("support.title")}</DialogTitle>
          <DialogDescription>{t("support.description")}</DialogDescription>
        </DialogHeader>
        {report === undefined ? null : (
          <div className="flex flex-col gap-4 text-sm">
            {report.installation === "desktop" ? <CopyReport report={report} /> : <ServerLog />}
            <div className="flex flex-col gap-2">
              <p>{t("support.sendStep", { email: SUPPORT_EMAIL })}</p>
              <ExternalLink
                href={issueUrl(report)}
                className={buttonVariants({
                  size: "sm",
                  className: "self-start text-primary-foreground hover:no-underline",
                })}
              >
                {t("support.github")}
              </ExternalLink>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
