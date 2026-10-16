import { useState } from "react";

import { useI18n } from "@/components/i18n/use-i18n";
import { ExternalLink } from "@/components/external-link";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ReportDialog } from "@/features/support/report-dialog";
import { UpdateSection } from "@/features/updates/update-notice";
import {
  APP_VERSION,
  CHANGELOG_URL,
  LICENSE_URL,
  MAKER,
  MAKER_URL,
  REPOSITORY_URL,
} from "@/lib/about";
import { isMachineTranslated } from "@/lib/locale";

export function AboutDialog({
  open,
  onOpenChange,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}) {
  const { t, locale } = useI18n();
  const [reportOpen, setReportOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("common.close")}>
        <DialogHeader>
          <div className="flex items-center gap-2">
            <img src="/favicon.svg" alt="" className="size-6" />
            <DialogTitle>{t("about.title")}</DialogTitle>
          </div>
          <p className="text-sm text-muted-foreground tabular-nums" data-app-version>
            {t("about.version", { version: APP_VERSION })}
          </p>
        </DialogHeader>
        <DialogDescription className="text-foreground">{t("about.description")}</DialogDescription>
        <ul className="flex flex-col gap-2 text-sm">
          <li>
            <ExternalLink href={LICENSE_URL} className="text-primary">
              {t("about.license")}
            </ExternalLink>
          </li>
          <li className="flex flex-wrap gap-x-4 gap-y-2">
            <ExternalLink href={REPOSITORY_URL} className="text-primary">
              {t("about.source")}
            </ExternalLink>
            <button
              type="button"
              className="inline-flex min-h-6 items-center text-primary underline-offset-4 hover:underline"
              onClick={() => {
                setReportOpen(true);
              }}
            >
              {t("about.reportBug")}
            </button>
            <ExternalLink href={CHANGELOG_URL} className="text-primary">
              {t("about.changelog")}
            </ExternalLink>
          </li>
        </ul>
        {isMachineTranslated(locale) ? (
          <p className="text-sm text-muted-foreground">
            {t("about.machineTranslated")}{" "}
            <button
              type="button"
              className="inline-flex min-h-6 items-center text-primary underline-offset-4 hover:underline"
              onClick={() => {
                setReportOpen(true);
              }}
            >
              {t("about.reportTranslation")}
            </button>
          </p>
        ) : null}
        <p className="text-xs text-muted-foreground">{t("about.noAdvice")}</p>
        <UpdateSection />
        <p className="border-t pt-4 text-sm text-muted-foreground">
          <ExternalLink href={MAKER_URL} icon={false} className="text-foreground">
            {t("about.madeBy", { maker: MAKER })}
          </ExternalLink>
        </p>
      </DialogContent>
      <ReportDialog open={reportOpen} onOpenChange={setReportOpen} />
    </Dialog>
  );
}
