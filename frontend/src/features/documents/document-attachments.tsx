import { useQuery } from "@tanstack/react-query";
import { FilePlusIcon, PaperclipIcon, XIcon } from "lucide-react";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  attachmentUrl,
  useAddAttachments,
  useDocumentAttachments,
  useRemoveAttachment,
  type Attachment,
} from "@/features/documents/api";
import { demoQuery } from "@/features/shared/demo-api";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { cn } from "@/lib/cn";
import { formatBytes } from "@/lib/format";

/** As many as the server takes for one draft (domain/document/attachment.py). */
const MAX_ATTACHMENTS = 10;

function AttachmentList({
  documentId,
  attachments,
  onRemove,
}: {
  readonly documentId: string;
  readonly attachments: readonly Attachment[];
  readonly onRemove?: ((attachment: Attachment) => void) | undefined;
}) {
  const { t, locale } = useI18n();
  return (
    <ul className="flex flex-col divide-y text-sm">
      {attachments.map((attachment) => (
        <li key={attachment.id} className="flex items-center gap-x-3 py-1.5">
          <a
            href={attachmentUrl(documentId, attachment.id)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-h-6 min-w-0 items-center gap-1.5 font-medium break-all text-primary underline-offset-4 hover:underline"
          >
            <PaperclipIcon className="size-3.5 shrink-0" aria-hidden="true" />
            {attachment.file_name}
            <span className="sr-only">{t("common.opensInNewTab")}</span>
          </a>
          <span className="text-xs whitespace-nowrap text-muted-foreground tabular-nums">
            {formatBytes(attachment.size, locale)}
          </span>
          {onRemove === undefined ? null : (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="ml-auto size-8 shrink-0"
              aria-label={t("documents.removeAttachment", { name: attachment.file_name })}
              onClick={() => {
                onRemove(attachment);
              }}
            >
              <XIcon aria-hidden="true" />
            </Button>
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * PDFs that go with a draft, e.g. the third-party invoices of pass-through items (ADR 0040).
 * They can be removed until the document is issued; then they are frozen with it and sent
 * after its PDF.
 */
export function DraftAttachments({ documentId }: { readonly documentId: string }) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const attachments = useDocumentAttachments(documentId);
  const add = useAddAttachments(documentId);
  const remove = useRemoveAttachment(documentId);
  // The public demo takes no uploads (the server refuses, too).
  const demo = useQuery(demoQuery).data?.enabled === true;
  const fail = (caught: unknown) => {
    toast.error(errorMessage(caught) ?? t("error.generic"), { duration: Infinity });
  };
  const full = (attachments?.length ?? 0) >= MAX_ATTACHMENTS;
  return (
    <div className="flex flex-col gap-3">
      {attachments === undefined || attachments.length === 0 ? null : (
        <AttachmentList
          documentId={documentId}
          attachments={attachments}
          onRemove={
            demo
              ? undefined
              : (attachment) => {
                  remove.mutate(attachment.id, {
                    onSuccess: () =>
                      toast.success(
                        t("documents.attachmentRemoved", { name: attachment.file_name }),
                      ),
                    onError: fail,
                  });
                }
          }
        />
      )}
      <p className="text-xs text-muted-foreground">{t("documents.draftAttachmentsNote")}</p>
      {demo || full ? null : (
        // The browser's own file button cannot be translated or styled; the label is the button.
        <label
          className={cn(
            buttonVariants({ variant: "outline", size: "sm" }),
            "w-fit cursor-pointer has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background",
            add.isPending && "pointer-events-none opacity-50",
          )}
        >
          <FilePlusIcon aria-hidden="true" />
          {add.isPending ? t("documents.attachmentsAdding") : t("documents.addPdf")}
          <input
            type="file"
            accept=".pdf,application/pdf"
            multiple
            className="sr-only"
            disabled={add.isPending}
            onChange={(event) => {
              const files = [...(event.target.files ?? [])];
              event.target.value = "";
              if (files.length === 0) return;
              add.mutate(files, {
                onSuccess: () =>
                  toast.success(t("documents.attachmentsAdded", { count: files.length })),
                onError: fail,
              });
            }}
          />
        </label>
      )}
    </div>
  );
}

/** The files issued with a document written here; nothing when there are none. */
export function IssuedAttachments({ documentId }: { readonly documentId: string }) {
  const { t } = useI18n();
  const attachments = useDocumentAttachments(documentId);
  if (attachments === undefined || attachments.length === 0) return null;
  return (
    <Card aria-labelledby="document-own-attachments">
      <CardHeader>
        <CardTitle id="document-own-attachments">{t("documents.attachmentsTitle")}</CardTitle>
        <CardDescription>{t("documents.issuedAttachmentsHint")}</CardDescription>
      </CardHeader>
      <AttachmentList documentId={documentId} attachments={attachments} />
    </Card>
  );
}
