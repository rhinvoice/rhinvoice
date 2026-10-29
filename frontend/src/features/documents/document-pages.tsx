import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import {
  ArchiveIcon,
  BanIcon,
  Building2Icon,
  CircleOffIcon,
  CircleCheckIcon,
  CopyIcon,
  DownloadIcon,
  EllipsisIcon,
  FileOutputIcon,
  FileTextIcon,
  HandCoinsIcon,
  ListIcon,
  PrinterIcon,
  RepeatIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
  Trash2Icon,
  MailIcon,
  Undo2Icon,
} from "lucide-react";
import { useState } from "react";
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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useDocumentTitle } from "@/components/use-document-title";
import { usePageShortcut } from "@/components/use-key-shortcuts";
import {
  documentHtmlQuery,
  documentKeys,
  documentPdfUrl,
  eInvoiceQuery,
  documentQuery,
  useAddPayment,
  useCreateDocument,
  useDeleteDocument,
  useDocumentAction,
  useMarkPaid,
  useRemovePayment,
  useRemoveWriteOff,
  useUpdateDocument,
  useWriteOff,
  type DocumentDetail,
} from "@/features/documents/api";
import { defaultTexts } from "@/features/documents/document-texts";
import { DocumentEditor, type EditableType } from "@/features/documents/document-editor";
import { documentToForm, emptyDocument } from "@/features/documents/document-form-model";
import { DocumentView } from "@/features/documents/document-view";
import { AttachmentsCard, ImportedPdf } from "@/features/documents/imported-document";
import { PaperPreview } from "@/components/paper-preview";
import { PaymentDialog } from "@/features/documents/payment-dialog";
import { RemoveWriteOffDialog, WriteOffDialog } from "@/features/documents/write-off-dialog";
import { canRemoveWriteOff, canWriteOff } from "@/features/documents/write-off-model";
import { fetchFile, saveFile } from "@/features/documents/file-download";
import { printPage } from "@/features/documents/print-page";
import { BackLink } from "@/features/shared/back-link";
import { companyQuery, type Company } from "@/features/shared/company-api";
import { DocumentStatusBadge } from "@/features/shared/document-status";
import { FormAlert } from "@/features/shared/form-alert";
import { SendMailDialog } from "@/features/shared/send-mail-dialog";
import { textTemplatesQuery } from "@/features/shared/texts-api";
import { showUndoToast } from "@/features/shared/undo";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { cn } from "@/lib/cn";
import { todayIso } from "@/lib/dates";
import { formatMoney } from "@/lib/format";
import type { MessageKey } from "@/lib/i18n";
import { readStorage, writeStorage } from "@/lib/storage";
import { termsFor } from "@/features/shared/country-profile-model";

const LIST_PATH = { invoice: "/invoices", cancellation: "/invoices", quote: "/quotes" } as const;
const LIST_TITLE = {
  invoice: "nav.invoices",
  cancellation: "nav.invoices",
  quote: "nav.quotes",
} as const satisfies Record<DocumentDetail["type"], MessageKey>;

function BackToList({ type }: { readonly type: DocumentDetail["type"] }) {
  const { t } = useI18n();
  return <BackLink to={LIST_PATH[type]} label={t(LIST_TITLE[type])} />;
}

function PageSkeleton() {
  const { t } = useI18n();
  return (
    <div className="flex flex-col gap-4" aria-busy="true" aria-label={t("app.loading")}>
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-96 w-full" />
    </div>
  );
}

/** Documents need the company (sender, currency, tax country). */
function useCompany(): { company: Company | null | undefined; error: unknown } {
  const query = useQuery(companyQuery);
  return { company: query.data, error: query.error };
}

function CompanyMissing() {
  const { t } = useI18n();
  return (
    <EmptyState
      icon={Building2Icon}
      title={t("documents.companyMissingTitle")}
      description={t("documents.companyMissing")}
      action={
        <Button asChild>
          <Link to="/settings">{t("nav.settings")}</Link>
        </Button>
      }
    />
  );
}

function issuedToast(t: ReturnType<typeof useI18n>["t"], document: DocumentDetail): string {
  const number = document.number ?? "";
  return document.type === "quote"
    ? t("documents.sentToast", { number })
    : t("documents.issuedToast", { number });
}

export function NewDocumentPage({
  type,
  customerId,
}: {
  readonly type: EditableType;
  readonly customerId?: string | undefined;
}) {
  const { t } = useI18n();
  const title = type === "quote" ? t("documents.newQuote") : t("documents.newInvoice");
  useDocumentTitle(t("app.pageTitle", { title }));
  const navigate = useNavigate();
  const { company, error } = useCompany();
  const errorMessage = useErrorMessage();
  const create = useCreateDocument();
  const issue = useDocumentAction("issue");
  // New documents start with the default texts; without templates they start empty.
  const templates = useQuery(textTemplatesQuery);

  if (error !== null) return <FormAlert message={errorMessage(error)} />;
  if (company === undefined || templates.isPending) return <PageSkeleton />;
  return (
    <>
      <BackToList type={type} />
      <PageHeader title={title} />
      {company === null ? (
        <CompanyMissing />
      ) : (
        <DocumentEditor
          type={type}
          company={company}
          isNew
          defaultValues={{
            // New documents start dated today; the date stays editable and may be cleared.
            ...emptyDocument(company, todayIso()),
            ...defaultTexts(templates.data ?? [], type, company.default_language),
            customer_id: customerId ?? "",
          }}
          onSave={(draft) => create.mutateAsync({ type, ...draft })}
          onSaved={async (saved, shouldIssue) => {
            // The draft exists now: whatever happens when issuing, continue on its
            // page so that a second click cannot create another draft.
            let message = t("documents.draftSaved");
            let failure: unknown = null;
            if (shouldIssue) {
              try {
                message = issuedToast(t, await issue.mutateAsync(saved.id));
              } catch (caught) {
                failure = caught;
              }
            }
            await navigate({
              to: "/documents/$documentId",
              params: { documentId: saved.id },
              replace: true,
            });
            if (failure === null) {
              toast.success(message);
            } else {
              toast.error(errorMessage(failure) ?? t("error.generic"), { duration: Infinity });
            }
          }}
        />
      )}
    </>
  );
}

export function DocumentPage({ documentId }: { readonly documentId: string }) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const query = useQuery(documentQuery(documentId));
  const { company, error } = useCompany();
  const document = query.data;
  useDocumentTitle(
    t("app.pageTitle", {
      title: document === undefined ? t("app.loading") : documentTitle(t, document),
    }),
  );
  if (query.isError || error !== null) {
    return <FormAlert message={errorMessage(query.error ?? error)} />;
  }
  if (document === undefined || company === undefined) return <PageSkeleton />;
  if (company === null) return <CompanyMissing />;
  return document.status === "draft" ? (
    <DraftPage key={document.id} document={document} company={company} />
  ) : (
    <IssuedPage document={document} company={company} />
  );
}

function documentTitle(t: ReturnType<typeof useI18n>["t"], document: DocumentDetail): string {
  const kind = t(`documentType.${document.type}`);
  return document.number === null
    ? t("documents.draftTitle", { kind })
    : t("documents.numberedTitle", { kind, number: document.number });
}

interface PageProps {
  readonly document: DocumentDetail;
  readonly company: Company;
}

function DraftPage({ document, company }: PageProps) {
  const { t, locale } = useI18n();
  const update = useUpdateDocument(document.id);
  const issue = useDocumentAction("issue");
  const type = document.type === "quote" ? "quote" : "invoice";
  return (
    <>
      <BackToList type={document.type} />
      <PageHeader
        title={documentTitle(t, document)}
        {...(document.recipient === null ? {} : { description: document.recipient.name })}
        actions={
          <>
            <DocumentStatusBadge status={document.display_status} />
            <MoreActions document={document} />
          </>
        }
      />
      <div className="flex flex-wrap gap-2 empty:hidden">
        <RelatedLinks document={document} />
      </div>
      <DocumentEditor
        type={type}
        company={company}
        isNew={false}
        autosave
        defaultValues={documentToForm(document, locale)}
        onSave={(draft) => update.mutateAsync(draft)}
        onSaved={async (saved, shouldIssue) => {
          if (!shouldIssue) {
            toast.success(t("common.saved"));
            return;
          }
          toast.success(issuedToast(t, await issue.mutateAsync(saved.id)));
        }}
      />
    </>
  );
}

function IssuedPage({ document, company }: PageProps) {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const client = useQueryClient();
  const [paymentOpen, setPaymentOpen] = useState(false);
  const addPayment = useAddPayment(document.id);
  const markPaid = useMarkPaid(document.id);
  const removePayment = useRemovePayment(document.id);
  const writeOff = useWriteOff(document.id);
  const removeWriteOff = useRemoveWriteOff(document.id);
  const [writeOffOpen, setWriteOffOpen] = useState(false);
  const [removeWriteOffOpen, setRemoveWriteOffOpen] = useState(false);
  const accept = useDocumentAction("accept");
  const decline = useDocumentAction("decline");
  const terms = termsFor(company.profile, locale);
  const tax = terms.tax_name;
  // Only invoices are paid: a cancellation reverses its invoice.
  const payable =
    document.type === "invoice" &&
    (document.status === "issued" || document.status === "partially_paid");
  const writtenOff = document.status === "written_off";
  const money = (amount: string) => formatMoney(amount, document.currency, locale);
  const fail = (caught: unknown) => {
    toast.error(errorMessage(caught) ?? t("error.generic"), { duration: Infinity });
  };

  const undoPayment = (changed: DocumentDetail) => {
    const payment = changed.payments.at(-1);
    if (payment === undefined) return;
    removePayment.mutate(payment.id, { onError: fail });
  };

  const onMarkPaid = () => {
    const key = documentKeys.detail(document.id);
    const previous = client.getQueryData<DocumentDetail>(key);
    // Optimistic: the document shows as paid at once and rolls back on error.
    client.setQueryData<DocumentDetail>(key, {
      ...document,
      status: "paid",
      display_status: "paid",
      open_amount: "0.00",
      paid_amount: document.totals.total,
    });
    markPaid.mutate(todayIso(), {
      onSuccess: (changed) => {
        showUndoToast(t("documents.markedPaid"), t("common.undo"), () => {
          undoPayment(changed);
        });
      },
      onError: (caught) => {
        client.setQueryData(key, previous);
        fail(caught);
      },
    });
  };

  usePageShortcut("p", () => {
    if (payable || writtenOff) setPaymentOpen(true);
  });
  const [view, setView] = useDocumentViewMode();
  const html = useQuery({
    ...documentHtmlQuery(document.id),
    // An imported invoice is its PDF: there is no page to render.
    enabled: view === "document" && !document.imported,
  });

  return (
    <>
      <BackToList type={document.type} />
      <PageHeader
        title={documentTitle(t, document)}
        description={`${document.recipient?.name ?? ""} · ${money(document.totals.total)}`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {document.imported ? (
              <Badge title={t("documents.importedHint")}>
                <ArchiveIcon aria-hidden="true" />
                {t("documents.imported")}
              </Badge>
            ) : null}
            <DocumentStatusBadge status={document.display_status} dueDate={document.due_date} />
          </div>
        }
      />
      <div className="flex flex-wrap items-center gap-2">
        {payable ? (
          <>
            <Button onClick={onMarkPaid} disabled={markPaid.isPending}>
              <CircleCheckIcon aria-hidden="true" />
              {t("documents.markPaid")}
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setPaymentOpen(true);
              }}
            >
              <HandCoinsIcon aria-hidden="true" />
              {t("documents.addPayment")}
            </Button>
          </>
        ) : null}
        {writtenOff ? (
          <Button
            variant="outline"
            onClick={() => {
              setPaymentOpen(true);
            }}
          >
            <HandCoinsIcon aria-hidden="true" />
            {t("documents.addPayment")}
          </Button>
        ) : null}
        {document.type === "quote" && document.status === "sent" ? (
          <>
            <Button
              variant="outline"
              onClick={() => {
                accept.mutate(document.id, {
                  onSuccess: () => toast.success(t("documents.acceptedToast")),
                  onError: fail,
                });
              }}
            >
              <ThumbsUpIcon aria-hidden="true" />
              {t("documents.accept")}
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                decline.mutate(document.id, {
                  onSuccess: () => toast.success(t("documents.declinedToast")),
                  onError: fail,
                });
              }}
            >
              <ThumbsDownIcon aria-hidden="true" />
              {t("documents.decline")}
            </Button>
          </>
        ) : null}
        <OutputActions documentId={document.id} printable={!document.imported} />
        <MailAction document={document} title={documentTitle(t, document)} />
        <RelatedLinks document={document} />
        <div className="ml-auto">
          <MoreActions
            document={document}
            onWriteOff={
              canWriteOff(document)
                ? () => {
                    setWriteOffOpen(true);
                  }
                : undefined
            }
            onRemoveWriteOff={
              canRemoveWriteOff(document)
                ? () => {
                    setRemoveWriteOffOpen(true);
                  }
                : undefined
            }
          />
        </div>
      </div>
      <div
        role="group"
        aria-label={t("documents.viewMode")}
        className="inline-flex w-fit gap-0.5 rounded-lg bg-muted p-1"
      >
        {(["document", "details"] as const).map((mode) => (
          <Button
            key={mode}
            size="sm"
            variant="ghost"
            aria-pressed={view === mode}
            className={cn(view === mode && "bg-card shadow-xs hover:bg-card")}
            onClick={() => {
              setView(mode);
            }}
          >
            {mode === "document" ? (
              <FileTextIcon aria-hidden="true" />
            ) : (
              <ListIcon aria-hidden="true" />
            )}
            {mode === "document" ? t("documents.viewDocument") : t("documents.viewDetails")}
          </Button>
        ))}
      </div>
      {view === "document" && document.imported ? (
        <div className="mx-auto w-full max-w-3xl">
          <ImportedPdf document={document} title={documentTitle(t, document)} />
        </div>
      ) : null}
      {view === "document" && !document.imported ? (
        <div className="mx-auto w-full max-w-3xl">
          <PaperPreview
            html={html.data}
            title={documentTitle(t, document)}
            busy={html.isFetching}
          />
        </div>
      ) : null}
      {document.imported ? (
        <div className="mx-auto w-full max-w-3xl">
          <AttachmentsCard document={document} />
        </div>
      ) : null}
      {view === "details" ? (
        <DocumentView
          document={document}
          taxName={tax}
          onRemovePayment={
            document.type === "invoice" && document.status !== "cancelled"
              ? (paymentId) => {
                  const removed = document.payments.find((payment) => payment.id === paymentId);
                  removePayment.mutate(paymentId, {
                    onSuccess: () => {
                      showUndoToast(t("documents.paymentRemoved"), t("common.undo"), () => {
                        if (removed === undefined) return;
                        // Undo records the same payment again.
                        addPayment.mutate(
                          { paidOn: removed.paid_on, amount: removed.amount, note: removed.note },
                          { onError: fail },
                        );
                      });
                    },
                    onError: fail,
                  });
                }
              : undefined
          }
        />
      ) : null}
      {canWriteOff(document) ? (
        <WriteOffDialog
          document={document}
          hint={terms.write_off_hint}
          open={writeOffOpen}
          onOpenChange={setWriteOffOpen}
          onSubmit={async (input) => {
            await writeOff.mutateAsync(input);
            showUndoToast(t("writeOff.done"), t("common.undo"), () => {
              removeWriteOff.mutate(undefined, { onError: fail });
            });
          }}
        />
      ) : null}
      <RemoveWriteOffDialog
        open={removeWriteOffOpen}
        onOpenChange={setRemoveWriteOffOpen}
        onConfirm={() => {
          removeWriteOff.mutate(undefined, {
            onSuccess: () => toast.success(t("writeOff.removed")),
            onError: fail,
          });
        }}
      />
      {payable || writtenOff ? (
        <PaymentDialog
          document={document}
          open={paymentOpen}
          onOpenChange={setPaymentOpen}
          onSubmit={async (payment) => {
            const changed = await addPayment.mutateAsync(payment);
            showUndoToast(
              t("documents.paymentAdded", { amount: money(payment.amount) }),
              t("common.undo"),
              () => {
                undoPayment(changed);
              },
            );
          }}
        />
      ) : null}
    </>
  );
}

/** Link between an invoice, its cancellation and the quote it came from. */
function RelatedLinks({ document }: { readonly document: DocumentDetail }) {
  const { t } = useI18n();
  const links: [string, string][] = [];
  if (document.source_id !== null) {
    links.push([
      document.source_id,
      document.type === "cancellation"
        ? t("documents.openCancelledInvoice")
        : t("documents.openSource"),
    ]);
  }
  if (document.converted_to_id !== null) {
    links.push([document.converted_to_id, t("documents.openConvertedInvoice")]);
  }
  if (document.cancelled_by_id !== null) {
    links.push([document.cancelled_by_id, t("documents.openCancellation")]);
  }
  return links.map(([target, label]) => (
    <Button key={target} asChild variant="link">
      <Link to="/documents/$documentId" params={{ documentId: target }}>
        {label}
      </Link>
    </Button>
  ));
}

type Confirmation = "delete" | "cancel" | null;

interface MoreActionsProps {
  readonly document: DocumentDetail;
  /** Opens the write-off dialog; left out where the invoice cannot be written off. */
  readonly onWriteOff?: (() => void) | undefined;
  readonly onRemoveWriteOff?: (() => void) | undefined;
}

function MoreActions({ document, onWriteOff, onRemoveWriteOff }: MoreActionsProps) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const errorMessage = useErrorMessage();
  const [confirm, setConfirm] = useState<Confirmation>(null);
  const duplicate = useDocumentAction("duplicate");
  const convert = useDocumentAction("convert");
  const cancel = useDocumentAction("cancel");
  const remove = useDeleteDocument();
  const fail = (caught: unknown) => {
    toast.error(errorMessage(caught) ?? t("error.generic"), { duration: Infinity });
  };
  const open = (created: DocumentDetail) =>
    navigate({ to: "/documents/$documentId", params: { documentId: created.id } });

  // Sent or accepted quotes become an invoice once (the server checks the same).
  const canConvert =
    document.type === "quote" &&
    (document.status === "sent" || document.status === "accepted") &&
    document.converted_to_id === null;
  // An imported invoice is its PDF: nothing can be built from its lines.
  const own = !document.imported;
  // A write-off still counts in its year: it is taken back before a cancellation.
  const canCancel =
    own &&
    document.write_off === null &&
    document.type === "invoice" &&
    (document.status === "issued" ||
      document.status === "partially_paid" ||
      document.status === "paid");
  const canDuplicate = own && document.type !== "cancellation";
  const canRecur = own && document.type === "invoice";
  const canDelete = document.status === "draft";
  const closing = onWriteOff !== undefined || onRemoveWriteOff !== undefined;
  if (!canConvert && !canCancel && !canDuplicate && !canDelete && !canRecur && !closing) {
    return null;
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="icon" aria-label={t("documents.moreActions")}>
            <EllipsisIcon aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-56">
          {canConvert ? (
            <DropdownMenuItem
              onSelect={() => {
                convert.mutate(document.id, {
                  onSuccess: (invoice) => {
                    toast.success(t("documents.convertedToast"));
                    void open(invoice);
                  },
                  onError: fail,
                });
              }}
            >
              <FileOutputIcon aria-hidden="true" />
              {t("documents.convert")}
            </DropdownMenuItem>
          ) : null}
          {canDuplicate ? (
            <DropdownMenuItem
              onSelect={() => {
                duplicate.mutate(document.id, {
                  onSuccess: (copy) => {
                    toast.success(t("documents.duplicatedToast"));
                    void open(copy);
                  },
                  onError: fail,
                });
              }}
            >
              <CopyIcon aria-hidden="true" />
              {t("documents.duplicate")}
            </DropdownMenuItem>
          ) : null}
          {canRecur ? (
            <DropdownMenuItem
              onSelect={() => {
                void navigate({ to: "/recurring/new", search: { from: document.id } });
              }}
            >
              <RepeatIcon aria-hidden="true" />
              {t("recurring.makeRecurring")}
            </DropdownMenuItem>
          ) : null}
          {canCancel || canDelete || closing ? <DropdownMenuSeparator /> : null}
          {onWriteOff === undefined ? null : (
            <DropdownMenuItem onSelect={onWriteOff}>
              <CircleOffIcon aria-hidden="true" />
              {t("writeOff.action")}
            </DropdownMenuItem>
          )}
          {onRemoveWriteOff === undefined ? null : (
            <DropdownMenuItem onSelect={onRemoveWriteOff}>
              <Undo2Icon aria-hidden="true" />
              {t("writeOff.remove")}
            </DropdownMenuItem>
          )}
          {canCancel ? (
            <DropdownMenuItem
              onSelect={() => {
                setConfirm("cancel");
              }}
            >
              <BanIcon aria-hidden="true" />
              {t("documents.cancel")}
            </DropdownMenuItem>
          ) : null}
          {canDelete ? (
            <DropdownMenuItem
              onSelect={() => {
                setConfirm("delete");
              }}
            >
              <Trash2Icon aria-hidden="true" />
              {t("documents.deleteDraft")}
            </DropdownMenuItem>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>

      <AlertDialog
        open={confirm !== null}
        onOpenChange={(next) => {
          if (!next) setConfirm(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirm === "cancel" ? t("documents.cancelTitle") : t("documents.deleteTitle")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirm === "cancel"
                ? t("documents.cancelDescription")
                : t("documents.deleteDescription")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              destructive
              onClick={() => {
                if (confirm === "cancel") {
                  cancel.mutate(document.id, {
                    onSuccess: (cancelled) => {
                      toast.success(t("documents.cancelledToast"));
                      if (cancelled.cancelled_by_id !== null) {
                        void navigate({
                          to: "/documents/$documentId",
                          params: { documentId: cancelled.cancelled_by_id },
                        });
                      }
                    },
                    onError: fail,
                  });
                } else {
                  remove.mutate(document.id, {
                    onSuccess: () => {
                      toast.success(t("documents.deletedToast"));
                      void navigate({ to: LIST_PATH[document.type] });
                    },
                    onError: fail,
                  });
                }
              }}
            >
              {confirm === "cancel" ? t("documents.cancel") : t("common.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

const VIEW_MODE_KEY = "rhinvoice.document-view";
type ViewMode = "document" | "details";

/** Issued documents open as paper; the choice is remembered in this browser. */
function useDocumentViewMode(): [ViewMode, (mode: ViewMode) => void] {
  const [mode, setMode] = useState<ViewMode>(() =>
    readStorage(VIEW_MODE_KEY) === "details" ? "details" : "document",
  );
  return [
    mode,
    (next) => {
      setMode(next);
      writeStorage(VIEW_MODE_KEY, next);
    },
  ];
}

/** Send the issued document by mail; invoices offer the XRechnung when it is complete. */
function MailAction({
  document,
  title,
}: {
  readonly document: DocumentDetail;
  readonly title: string;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const eInvoice = useQuery({
    ...eInvoiceQuery(document.id),
    enabled: document.type !== "quote" && !document.imported,
  });
  return (
    <>
      <Button
        variant="outline"
        onClick={() => {
          setOpen(true);
        }}
      >
        <MailIcon aria-hidden="true" />
        {t("mail.sendAction")}
      </Button>
      <SendMailDialog
        subject={{ kind: "document", id: document.id }}
        title={title}
        open={open}
        onOpenChange={setOpen}
        xrechnung={document.type !== "quote" && eInvoice.data?.xrechnung_problems.length === 0}
        warning={document.status === "cancelled" ? t("mail.cancelledWarning") : undefined}
      />
    </>
  );
}

/** PDF in the browser, as a download, and printing (the same page as the PDF). */
function OutputActions({
  documentId,
  printable,
}: {
  readonly documentId: string;
  /** Imported invoices have no page to print: the PDF is the invoice. */
  readonly printable: boolean;
}) {
  const { t } = useI18n();
  const client = useQueryClient();
  const errorMessage = useErrorMessage();
  const [busy, setBusy] = useState(false);
  const fail = (caught: unknown) => {
    toast.error(errorMessage(caught) ?? t("error.generic"), { duration: Infinity });
  };
  // The first PDF of an issued invoice archives it with its e-invoice.
  const archived = () => client.invalidateQueries({ queryKey: eInvoiceQuery(documentId).queryKey });

  const show = () => {
    // Opened right away: browsers only allow new tabs directly after a click.
    const tab = window.open("", "_blank");
    setBusy(true);
    fetchFile(documentPdfUrl(documentId), "document.pdf")
      .then(
        (file) => {
          if (tab === null) {
            fail(new Error(t("documents.popupBlocked")));
            return;
          }
          tab.location.href = URL.createObjectURL(file.blob);
          void archived();
        },
        (caught: unknown) => {
          tab?.close();
          fail(caught);
        },
      )
      .finally(() => {
        setBusy(false);
      });
  };

  const download = () => {
    setBusy(true);
    fetchFile(documentPdfUrl(documentId, true), "document.pdf")
      .then((file) => {
        saveFile(file);
        void archived();
      }, fail)
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <>
      <Button variant="outline" disabled={busy} onClick={show}>
        <FileTextIcon aria-hidden="true" />
        {t("documents.pdf")}
        <span className="sr-only">{t("common.opensInNewTab")}</span>
      </Button>
      <Button variant="outline" disabled={busy} onClick={download}>
        <DownloadIcon aria-hidden="true" />
        {t("documents.download")}
      </Button>
      {printable ? (
        <Button
          variant="outline"
          onClick={() => {
            client.query(documentHtmlQuery(documentId)).then(printPage, fail);
          }}
        >
          <PrinterIcon aria-hidden="true" />
          {t("documents.print")}
        </Button>
      ) : null}
    </>
  );
}
