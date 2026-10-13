import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FilePlusIcon, FileTextIcon, PaperclipIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
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
import { buttonVariants } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import {
  attachmentUrl,
  attachmentsQuery,
  documentPdfQuery,
  releaseDocumentPdf,
  useAddFile,
  type DocumentDetail,
} from "@/features/documents/api";
import { demoQuery } from "@/features/shared/demo-api";
import { FormAlert } from "@/features/shared/form-alert";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { cn } from "@/lib/cn";
import { formatDate, formatBytes } from "@/lib/format";

// The sheet fitted to the width, without the thumbnails the browser's PDF viewer would
// spend a third of the frame on; its toolbar (zoom, print, download) stays. Chromium
// browsers follow these "open parameters"; a browser that does not shows its viewer as before.
const FIT_WIDTH = "#navpanes=0&view=FitH";

/** The original PDF of an invoice taken over from another program, shown on the page. */
export function ImportedPdf({
  document,
  title,
}: {
  readonly document: DocumentDetail;
  readonly title: string;
}) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const client = useQueryClient();
  const pdf = useQuery({ ...documentPdfQuery(document.id), enabled: document.has_pdf });
  useEffect(
    () => () => {
      releaseDocumentPdf(client, document.id);
    },
    [client, document.id],
  );

  if (!document.has_pdf) {
    return (
      <Card>
        <EmptyState
          icon={FileTextIcon}
          title={t("documents.noPdf")}
          description={t("documents.noPdfHint")}
          action={<AddFileButton document={document} primary />}
        />
      </Card>
    );
  }
  if (pdf.isError) return <FormAlert message={errorMessage(pdf.error)} />;
  const url = pdf.data;
  return url === undefined ? (
    <div aria-busy="true" aria-label={t("documents.pdfLoading")}>
      <Skeleton className="h-[80vh] w-full" />
    </div>
  ) : (
    <iframe
      src={`${url}${FIT_WIDTH}`}
      title={`${title} · ${t("documents.originalPdf")}`}
      className="h-[80vh] w-full rounded-lg border bg-card"
    />
  );
}

/** Reminders, corrections and copies kept with an imported invoice. */
export function AttachmentsCard({ document }: { readonly document: DocumentDetail }) {
  const { t, locale } = useI18n();
  const attachments = useQuery(attachmentsQuery(document.id)).data;
  return (
    <Card aria-labelledby="document-attachments">
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-1.5">
          <CardTitle id="document-attachments">{t("documents.attachmentsTitle")}</CardTitle>
          <CardDescription>{t("documents.attachmentsHint")}</CardDescription>
        </div>
        {document.has_pdf ? <AddFileButton document={document} /> : null}
      </CardHeader>
      {attachments === undefined ? (
        <div aria-busy="true" aria-label={t("app.loading")}>
          <Skeleton className="h-10 w-full" />
        </div>
      ) : attachments.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("documents.attachmentsEmpty")}</p>
      ) : (
        <ul className="flex flex-col divide-y text-sm">
          {attachments.map((attachment) => (
            <li key={attachment.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
              <a
                href={attachmentUrl(document.id, attachment.id)}
                target="_blank"
                rel="noreferrer"
                className="inline-flex min-h-6 min-w-0 items-center gap-1.5 font-medium break-all text-primary underline-offset-4 hover:underline"
              >
                <PaperclipIcon className="size-3.5 shrink-0" aria-hidden="true" />
                {attachment.file_name}
                <span className="sr-only">{t("common.opensInNewTab")}</span>
              </a>
              <span className="text-xs text-muted-foreground tabular-nums">
                {formatBytes(attachment.size, locale)} ·{" "}
                {formatDate(attachment.added_at.slice(0, 10), locale)}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">{t("documents.addFileHint")}</p>
    </Card>
  );
}

/** Choose a PDF for the invoice: its original while it has none, else an attachment. */
function AddFileButton({
  document,
  primary = false,
}: {
  readonly document: DocumentDetail;
  readonly primary?: boolean;
}) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const add = useAddFile(document.id);
  // The public demo keeps its documents as they are (the server refuses, too).
  const demo = useQuery(demoQuery).data?.enabled === true;
  const [chosen, setChosen] = useState<File | null>(null);
  if (demo) return null;
  const original = !document.has_pdf;
  return (
    <>
      {/* The browser's own file button cannot be translated or styled; the label is the button. */}
      <label
        className={cn(
          buttonVariants({
            variant: primary ? "default" : "outline",
            size: primary ? "default" : "sm",
          }),
          "cursor-pointer has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background",
          add.isPending && "pointer-events-none opacity-50",
        )}
      >
        <FilePlusIcon aria-hidden="true" />
        {original ? t("documents.addPdf") : t("documents.addAttachment")}
        <input
          type="file"
          accept=".pdf,application/pdf"
          className="sr-only"
          disabled={add.isPending}
          onChange={(event) => {
            setChosen(event.target.files?.[0] ?? null);
            event.target.value = "";
          }}
        />
      </label>
      {/* A file added stays for good (GoBD): say so before it is sent. */}
      <AlertDialog
        open={chosen !== null}
        onOpenChange={(open) => {
          if (!open) setChosen(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {original ? t("documents.addPdfTitle") : t("documents.addAttachmentTitle")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("documents.addFileConfirm", { name: chosen?.name ?? "" })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (chosen === null) return;
                add.mutate(chosen, {
                  onSuccess: () => {
                    toast.success(original ? t("documents.pdfAdded") : t("documents.fileAdded"));
                  },
                  onError: (caught) => {
                    toast.error(errorMessage(caught) ?? t("error.generic"), {
                      duration: Infinity,
                    });
                  },
                });
              }}
            >
              {original ? t("documents.addPdf") : t("documents.addAttachment")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
