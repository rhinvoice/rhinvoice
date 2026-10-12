import { useQuery } from "@tanstack/react-query";
import { DownloadIcon, FileCheckIcon, FileXIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import {
  eInvoiceQuery,
  xrechnungUrl,
  type EInvoiceProblem,
  type EInvoiceStatus,
} from "@/features/documents/api";
import { fetchFile, saveFile } from "@/features/documents/file-download";
import { useErrorMessage } from "@/features/shared/use-error-message";

/** Whether the PDF of an issued invoice is an e-invoice, and its XRechnung. */
export function EInvoiceCard({ documentId }: { readonly documentId: string }) {
  const { t } = useI18n();
  const status = useQuery(eInvoiceQuery(documentId)).data;
  if (status === undefined) return null;
  return (
    <Card aria-labelledby="document-e-invoice">
      <CardHeader>
        <CardTitle id="document-e-invoice">{t("eInvoice.title")}</CardTitle>
      </CardHeader>
      <div className="flex flex-col gap-3 text-sm">
        <ZugferdStatus status={status} />
        {/* XRechnung matters for German authorities only: out of the way for everyone else. */}
        <details className="group">
          <summary className="min-h-6 cursor-pointer text-muted-foreground hover:text-foreground">
            {t("eInvoice.xrechnungSummary")}
          </summary>
          <div className="mt-2">
            <XRechnung documentId={documentId} problems={status.xrechnung_problems} />
          </div>
        </details>
        {status.zugferd_problems.length > 0 || status.xrechnung_problems.length > 0 ? (
          <p className="text-xs text-muted-foreground">{t("eInvoice.nextTime")}</p>
        ) : null}
      </div>
    </Card>
  );
}

function ZugferdStatus({ status }: { readonly status: EInvoiceStatus }) {
  const { t } = useI18n();
  // Archived PDFs say what they hold; before, the settings and the data decide.
  const embedded = status.embedded ?? (status.enabled && status.zugferd_problems.length === 0);
  if (embedded) {
    return (
      <p className="flex gap-2">
        <FileCheckIcon className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
        {status.embedded === null ? t("eInvoice.pending") : t("eInvoice.embedded")}
      </p>
    );
  }
  return (
    <div className="flex gap-2">
      <FileXIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <div className="flex flex-col gap-1">
        <p>{t("eInvoice.notEmbedded")}</p>
        {status.enabled ? null : <p className="text-muted-foreground">{t("eInvoice.disabled")}</p>}
        {status.enabled && status.zugferd_problems.length === 0 ? (
          <p className="text-muted-foreground">{t("eInvoice.beforeEInvoices")}</p>
        ) : null}
        <EInvoiceProblems label={t("eInvoice.missing")} problems={status.zugferd_problems} />
      </div>
    </div>
  );
}

function XRechnung({
  documentId,
  problems,
}: {
  readonly documentId: string;
  readonly problems: readonly EInvoiceProblem[];
}) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const [busy, setBusy] = useState(false);
  if (problems.length > 0) {
    return <EInvoiceProblems label={t("eInvoice.xrechnungMissing")} problems={problems} />;
  }
  return (
    <div className="flex flex-col items-start gap-1">
      <Button
        variant="outline"
        size="sm"
        disabled={busy}
        aria-describedby="document-xrechnung-hint"
        onClick={() => {
          setBusy(true);
          fetchFile(xrechnungUrl(documentId), "xrechnung.xml")
            .then(saveFile, (caught: unknown) => {
              toast.error(errorMessage(caught) ?? t("error.generic"));
            })
            .finally(() => {
              setBusy(false);
            });
        }}
      >
        <DownloadIcon aria-hidden="true" />
        {t("eInvoice.xrechnung")}
      </Button>
      <p id="document-xrechnung-hint" className="text-xs text-muted-foreground">
        {t("eInvoice.xrechnungHint")}
      </p>
    </div>
  );
}

/** What keeps an invoice from being an e-invoice, with where to add it. */
export function EInvoiceProblems({
  label,
  problems,
}: {
  readonly label: string;
  readonly problems: readonly EInvoiceProblem[];
}) {
  const { t } = useI18n();
  if (problems.length === 0) return null;
  return (
    <div className="flex flex-col gap-1">
      <p className="text-muted-foreground">{label}</p>
      <ul className="list-disc pl-5">
        {problems.map((problem) => (
          <li key={problem}>{t(`eInvoice.problem.${problem}`)}</li>
        ))}
      </ul>
    </div>
  );
}
