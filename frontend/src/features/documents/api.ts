import {
  keepPreviousData,
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import { api, CLIENT_HEADER, unwrap, type components } from "@/api/client";
import { fetchFile } from "@/features/shared/file-download";
import { markItemsPaid } from "@/features/documents/paid-rows";
import {
  useIdempotentMutation,
  type IdempotencyHeaders,
} from "@/features/shared/use-idempotent-mutation";
import { toApiError } from "@/lib/api-error";

export type DocumentDetail = components["schemas"]["DocumentResponse"];
export type DocumentSummary = components["schemas"]["SummaryResponse"];
export type DocumentType = components["schemas"]["DocumentType"];
export type DisplayStatus = components["schemas"]["DisplayStatus"];
export type DocumentSort = components["schemas"]["DocumentSort"];
export type DraftRequest = components["schemas"]["DraftRequest"];
export type CreateRequest = components["schemas"]["CreateRequest"];
export type Totals = components["schemas"]["TotalsResponse"];
export type TaxTreatment = components["schemas"]["TaxTreatment"];
export type CustomerOption = components["schemas"]["CustomerResponse"];
export type ArticleOption = components["schemas"]["ArticleResponse"];
export type ArticleRequest = components["schemas"]["ArticleRequest"];
export type DocumentPage = components["schemas"]["DocumentPage"];
export type CurrencyTotals = components["schemas"]["CurrencyTotalsResponse"];
export type RecordedPayment = components["schemas"]["RecordedPaymentSchema"];
export type Attachment = components["schemas"]["AttachmentResponse"];
export type BadDebtYear = components["schemas"]["BadDebtYearResponse"];

export interface DocumentListParams {
  readonly types: readonly DocumentType[];
  readonly statuses: readonly DisplayStatus[];
  readonly customerId?: string;
  readonly year?: number;
  readonly q: string;
  readonly sort: DocumentSort;
  readonly direction: "asc" | "desc";
  readonly offset: number;
  readonly limit: number;
}

export const documentKeys = {
  all: ["documents"] as const,
  lists: ["documents", "list"] as const,
  list: (params: DocumentListParams) => ["documents", "list", params] as const,
  detail: (id: string) => ["documents", "detail", id] as const,
  dashboard: ["dashboard"] as const,
  badDebts: ["bad-debts"] as const,
  /** The dunning overview (features/dunning) lists the overdue invoices. */
  dunning: ["dunning"] as const,
};

export function documentListQuery(params: DocumentListParams) {
  return queryOptions({
    queryKey: documentKeys.list(params),
    queryFn: () =>
      unwrap(
        api.GET("/api/documents", {
          params: {
            query: {
              type: [...params.types],
              status: [...params.statuses],
              ...(params.customerId === undefined ? {} : { customer_id: params.customerId }),
              ...(params.year === undefined ? {} : { year: params.year }),
              q: params.q,
              sort: params.sort,
              direction: params.direction,
              limit: params.limit,
              offset: params.offset,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function documentQuery(id: string) {
  return queryOptions({
    queryKey: documentKeys.detail(id),
    queryFn: () =>
      unwrap(api.GET("/api/documents/{document_id}", { params: { path: { document_id: id } } })),
  });
}

/** Customers and articles for the pickers in the editor (active ones only). */
export function customerOptionsQuery(q: string) {
  return queryOptions({
    queryKey: ["customers", "options", q],
    queryFn: () =>
      unwrap(api.GET("/api/customers", { params: { query: { q, limit: 20, sort: "name" } } })),
    placeholderData: keepPreviousData,
  });
}

export function customerOptionQuery(id: string) {
  return queryOptions({
    queryKey: ["customers", "detail", id],
    queryFn: () =>
      unwrap(api.GET("/api/customers/{customer_id}", { params: { path: { customer_id: id } } })),
  });
}

export function articleOptionsQuery(q: string) {
  return queryOptions({
    queryKey: ["articles", "options", q],
    queryFn: () =>
      unwrap(api.GET("/api/articles", { params: { query: { q, limit: 8, sort: "name" } } })),
    placeholderData: keepPreviousData,
  });
}

/** Save a typed position as an article, so the line search finds it next time. */
export function useCreateArticle() {
  const client = useQueryClient();
  return useIdempotentMutation({
    mutationFn: (body: ArticleRequest, { headers }) =>
      unwrap(api.POST("/api/articles", { body, headers })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["articles"] });
    },
  });
}

/** Store the changed document and refresh everything that summarises documents. */
function useOnChanged() {
  const client = useQueryClient();
  return (document: DocumentDetail) => {
    client.setQueryData(documentKeys.detail(document.id), document);
    void client.invalidateQueries({ queryKey: documentKeys.lists });
    void client.invalidateQueries({ queryKey: documentKeys.dashboard });
    void client.invalidateQueries({ queryKey: documentKeys.badDebts });
    void client.invalidateQueries({ queryKey: documentKeys.dunning });
  };
}

export function useCreateDocument() {
  const onSuccess = useOnChanged();
  return useIdempotentMutation({
    mutationFn: (body: CreateRequest, { headers }) =>
      unwrap(api.POST("/api/documents", { body, headers })),
    onSuccess,
  });
}

export function useUpdateDocument(id: string) {
  const onSuccess = useOnChanged();
  return useMutation({
    mutationFn: (body: DraftRequest) =>
      unwrap(
        api.PUT("/api/documents/{document_id}", { params: { path: { document_id: id } }, body }),
      ),
    onSuccess,
  });
}

export function useDeleteDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/api/documents/{document_id}", { params: { path: { document_id: id } } })),
    onSuccess: (_result, id) => {
      client.removeQueries({ queryKey: documentKeys.detail(id) });
      void client.invalidateQueries({ queryKey: documentKeys.lists });
    },
  });
}

type Action = "issue" | "accept" | "decline" | "cancel" | "duplicate";

const byId = (id: string, { headers }: IdempotencyHeaders) => ({
  params: { path: { document_id: id } },
  headers,
});

const ACTIONS: Readonly<
  Record<Action, (id: string, idempotent: IdempotencyHeaders) => Promise<DocumentDetail>>
> = {
  issue: (id, key) => unwrap(api.POST("/api/documents/{document_id}/issue", byId(id, key))),
  accept: (id, key) => unwrap(api.POST("/api/documents/{document_id}/accept", byId(id, key))),
  decline: (id, key) => unwrap(api.POST("/api/documents/{document_id}/decline", byId(id, key))),
  cancel: (id, key) => unwrap(api.POST("/api/documents/{document_id}/cancel", byId(id, key))),
  duplicate: (id, key) => unwrap(api.POST("/api/documents/{document_id}/duplicate", byId(id, key))),
};

/** Lifecycle actions without a body; "duplicate" returns the new draft. */
export function useDocumentAction(action: Action) {
  return useSourceAction(ACTIONS[action]);
}

export interface ConvertInput {
  readonly id: string;
  /** The items the customer took; undefined: those in the quote's total (ADR 0045). */
  readonly lineIds?: readonly string[];
}

/** Turn a quote into an invoice draft, which it returns. */
export function useConvertQuote() {
  return useSourceAction(({ id, lineIds }: ConvertInput, key: IdempotencyHeaders) =>
    unwrap(
      api.POST("/api/documents/{document_id}/convert", {
        ...byId(id, key),
        ...(lineIds === undefined ? {} : { body: { line_ids: [...lineIds] } }),
      }),
    ),
  );
}

/** An action on a document that may change another one too (the draft it creates). */
function useSourceAction<TVariables extends string | { readonly id: string }>(
  mutationFn: (variables: TVariables, idempotent: IdempotencyHeaders) => Promise<DocumentDetail>,
) {
  const onSuccess = useOnChanged();
  const client = useQueryClient();
  const idOf = (variables: TVariables) =>
    typeof variables === "string" ? variables : variables.id;
  return useIdempotentMutation({
    mutationFn,
    onSuccess: (document, variables) => {
      onSuccess(document);
      // The source changed too: a converted quote gets an event, a cancelled
      // invoice points to its cancellation.
      const id = idOf(variables);
      if (document.id !== id) void client.invalidateQueries({ queryKey: documentKeys.detail(id) });
    },
    // A failed response does not prove a failed action (e.g. the connection broke
    // after the server committed): show the document as the server has it.
    onError: (_error, variables) => {
      void client.invalidateQueries({ queryKey: documentKeys.detail(idOf(variables)) });
      void client.invalidateQueries({ queryKey: documentKeys.lists });
    },
  });
}

export interface PaymentInput {
  readonly paidOn: string;
  readonly amount: string;
  readonly note: string;
}

export function useAddPayment(id: string) {
  const onSuccess = useOnChanged();
  return useIdempotentMutation({
    mutationFn: (payment: PaymentInput, { headers }) =>
      unwrap(
        api.POST("/api/documents/{document_id}/payments", {
          params: { path: { document_id: id } },
          body: { paid_on: payment.paidOn, amount: payment.amount, note: payment.note },
          headers,
        }),
      ),
    onSuccess,
  });
}

export function useMarkPaid(id: string) {
  const onSuccess = useOnChanged();
  return useIdempotentMutation({
    mutationFn: (paidOn: string, { headers }) =>
      unwrap(
        api.POST("/api/documents/{document_id}/mark-paid", {
          params: { path: { document_id: id } },
          body: { paid_on: paidOn },
          headers,
        }),
      ),
    onSuccess,
  });
}

/** Refresh everything that shows these documents after a bulk change. */
function useOnManyChanged() {
  const client = useQueryClient();
  return (ids: readonly string[]) => {
    for (const id of ids) void client.invalidateQueries({ queryKey: documentKeys.detail(id) });
    void client.invalidateQueries({ queryKey: documentKeys.lists });
    void client.invalidateQueries({ queryKey: documentKeys.dashboard });
  };
}

/** Pay several invoices in full at once (all or none); returns the payments to undo it. */
export function useMarkPaidMany() {
  const client = useQueryClient();
  const onChanged = useOnManyChanged();
  return useIdempotentMutation({
    // Without a date the server uses today in the installation's time zone.
    mutationFn: (ids: readonly string[], { headers }) =>
      unwrap(api.POST("/api/documents/mark-paid", { body: { document_ids: [...ids] }, headers })),
    // Optimistic: the rows show as paid at once and roll back on an error.
    onMutate: async (ids) => {
      await client.cancelQueries({ queryKey: documentKeys.lists });
      const previous = client.getQueriesData<DocumentPage>({ queryKey: documentKeys.lists });
      client.setQueriesData<DocumentPage>({ queryKey: documentKeys.lists }, (page) =>
        page === undefined ? page : { ...page, items: markItemsPaid(page.items, ids) },
      );
      return { previous };
    },
    onError: (_error, _ids, context) => {
      for (const [key, page] of context?.previous ?? []) client.setQueryData(key, page);
    },
    onSettled: (_result, _error, ids) => {
      onChanged(ids);
    },
  });
}

/** Remove several payments at once, e.g. to undo {@link useMarkPaidMany}. */
export function useRemovePayments() {
  const onChanged = useOnManyChanged();
  return useIdempotentMutation({
    mutationFn: (payments: readonly RecordedPayment[], { headers }) =>
      unwrap(
        api.POST("/api/documents/remove-payments", { body: { payments: [...payments] }, headers }),
      ),
    onSuccess: (_result, payments) => {
      onChanged(payments.map((payment) => payment.document_id));
    },
  });
}

export function useRemovePayment(id: string) {
  const onSuccess = useOnChanged();
  return useMutation({
    mutationFn: (paymentId: string) =>
      unwrap(
        api.DELETE("/api/documents/{document_id}/payments/{payment_id}", {
          params: { path: { document_id: id, payment_id: paymentId } },
        }),
      ),
    onSuccess,
  });
}

export interface WriteOffInput {
  readonly writtenOffOn: string;
  readonly reason: components["schemas"]["WriteOffReason"];
  readonly note: string;
}

/** Give up collecting the open rest of an invoice; the invoice itself stays as issued. */
export function useWriteOff(id: string) {
  const onSuccess = useOnChanged();
  return useIdempotentMutation({
    mutationFn: (writeOff: WriteOffInput, { headers }) =>
      unwrap(
        api.POST("/api/documents/{document_id}/write-off", {
          params: { path: { document_id: id } },
          body: {
            written_off_on: writeOff.writtenOffOn,
            reason: writeOff.reason,
            note: writeOff.note,
          },
          headers,
        }),
      ),
    onSuccess,
  });
}

export function useRemoveWriteOff(id: string) {
  const onSuccess = useOnChanged();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.DELETE("/api/documents/{document_id}/write-off", {
          params: { path: { document_id: id } },
        }),
      ),
    onSuccess,
  });
}

/** Written-off amounts per year and currency, the latest year first. */
export function badDebtsQuery() {
  return queryOptions({
    queryKey: documentKeys.badDebts,
    queryFn: () => unwrap(api.GET("/api/bad-debts")),
  });
}

export type Preview = components["schemas"]["DocumentPreviewResponse"];

/** The draft as a page of the print template, for the live preview. */
export function renderQuery(body: CreateRequest | null) {
  return queryOptions({
    queryKey: ["documents", "render", body] as const,
    queryFn: () => {
      if (body === null) throw new Error("the render query is disabled without a request");
      return unwrap(api.POST("/api/documents/render", { body, parseAs: "text" }));
    },
    enabled: body !== null,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
    retry: false,
  });
}

/** An existing document as a page of the print template. */
export function documentHtmlQuery(id: string) {
  return queryOptions({
    queryKey: ["documents", "html", id] as const,
    queryFn: () =>
      unwrap(
        api.GET("/api/documents/{document_id}/html", {
          params: { path: { document_id: id } },
          parseAs: "text",
        }),
      ),
  });
}

/** Live totals of the draft in the editor; the server is the only place that calculates. */
export function previewQuery(body: CreateRequest | null) {
  return queryOptions({
    queryKey: ["documents", "preview", body],
    queryFn: () => {
      if (body === null) throw new Error("the preview query is disabled without a request");
      return unwrap(api.POST("/api/documents/preview", { body }));
    },
    enabled: body !== null,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
    retry: false,
  });
}

/** Address of the PDF of a saved document (issued ones always return the archived file). */
export function documentPdfUrl(id: string, download = false): string {
  return `/api/documents/${encodeURIComponent(id)}/pdf${download ? "?download=true" : ""}`;
}

export type EInvoiceStatus = components["schemas"]["EInvoiceStatusResponse"];
export type EInvoiceProblem = EInvoiceStatus["zugferd_problems"][number];

/** Whether an issued invoice is (or will be) an e-invoice, and what keeps it from one. */
export function eInvoiceQuery(documentId: string) {
  return queryOptions({
    queryKey: ["documents", "e-invoice", documentId] as const,
    queryFn: () =>
      unwrap(
        api.GET("/api/documents/{document_id}/e-invoice", {
          params: { path: { document_id: documentId } },
        }),
      ),
  });
}

export function xrechnungUrl(documentId: string): string {
  return `/api/documents/${encodeURIComponent(documentId)}/xrechnung`;
}

/** The payment reminders of an invoice. */
export function remindersQuery(documentId: string) {
  return queryOptions({
    queryKey: ["documents", "reminders", documentId] as const,
    queryFn: () =>
      unwrap(
        api.GET("/api/documents/{document_id}/reminders", {
          params: { path: { document_id: documentId } },
        }),
      ),
  });
}

/** Further files: of an invoice taken over from another program, or of a document written here. */
export function attachmentsQuery(documentId: string) {
  return queryOptions({
    queryKey: ["documents", "attachments", documentId] as const,
    queryFn: () =>
      unwrap(
        api.GET("/api/documents/{document_id}/attachments", {
          params: { path: { document_id: documentId } },
        }),
      ),
  });
}

/** The files of a document; none asked for while a draft was not saved yet (null). */
export function useDocumentAttachments(documentId: string | null): Attachment[] | undefined {
  return useQuery({ ...attachmentsQuery(documentId ?? ""), enabled: documentId !== null }).data;
}

export function attachmentUrl(documentId: string, attachmentId: string, download = false): string {
  const document = encodeURIComponent(documentId);
  const attachment = encodeURIComponent(attachmentId);
  return `/api/documents/${document}/attachments/${attachment}${download ? "?download=true" : ""}`;
}

/** The archived PDF of a document as a local address for a frame (the API's may not be framed).

Whoever shows it releases it with ``releaseDocumentPdf``.
*/
export function documentPdfQuery(documentId: string) {
  return queryOptions({
    queryKey: ["documents", "pdf", documentId] as const,
    queryFn: async () => {
      const file = await fetchFile(documentPdfUrl(documentId), "document.pdf");
      return URL.createObjectURL(file.blob);
    },
    staleTime: Infinity,
  });
}

/** Free the local copy of a PDF shown on a page that is left. */
export function releaseDocumentPdf(client: QueryClient, documentId: string): void {
  const { queryKey } = documentPdfQuery(documentId);
  const url = client.getQueryData(queryKey);
  if (url !== undefined) URL.revokeObjectURL(url);
  client.removeQueries({ queryKey });
}

/** Send a PDF to a document (multipart: the generated client posts JSON only). */
async function postFile(
  documentId: string,
  file: File,
  { headers }: IdempotencyHeaders,
): Promise<DocumentDetail> {
  const body = new FormData();
  body.append("file", file);
  let response: Response;
  try {
    response = await fetch(`/api/documents/${encodeURIComponent(documentId)}/files`, {
      method: "POST",
      body,
      credentials: "same-origin",
      headers: { [CLIENT_HEADER]: "web", ...headers },
    });
  } catch {
    throw toApiError(0, undefined);
  }
  if (!response.ok) {
    throw toApiError(response.status, await response.json().catch(() => undefined));
  }
  return (await response.json()) as DocumentDetail;
}

/**
 * Refresh the files of a document and the document itself, whose history notes each file
 * added or removed. The draft's form keeps what is being edited: it only starts from the
 * document.
 */
function useOnFilesChanged(documentId: string) {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: attachmentsQuery(documentId).queryKey }),
      client.invalidateQueries({ queryKey: documentKeys.detail(documentId) }),
    ]);
}

/** Attach PDFs to a draft, one after the other (ADR 0040). */
export function useAddAttachments(documentId: string) {
  const onSettled = useOnFilesChanged(documentId);
  return useIdempotentMutation({
    mutationFn: async (files: readonly File[], { part }) => {
      for (const [index, file] of files.entries()) await postFile(documentId, file, part(index));
    },
    onSettled,
  });
}

/** Attach the PDFs chosen before a new draft had been saved, once it exists. */
export function useAttachToNewDraft() {
  const client = useQueryClient();
  return useIdempotentMutation({
    mutationFn: async (
      { documentId, files }: { documentId: string; files: readonly File[] },
      { part },
    ) => {
      for (const [index, file] of files.entries()) await postFile(documentId, file, part(index));
    },
    onSettled: (_data, _error, { documentId }) =>
      Promise.all([
        client.invalidateQueries({ queryKey: attachmentsQuery(documentId).queryKey }),
        client.invalidateQueries({ queryKey: documentKeys.detail(documentId) }),
      ]),
  });
}

/** Take an attachment off a draft; issued documents keep theirs. */
export function useRemoveAttachment(documentId: string) {
  const onSettled = useOnFilesChanged(documentId);
  return useMutation({
    mutationFn: (attachmentId: string) =>
      unwrap(
        api.DELETE("/api/documents/{document_id}/attachments/{attachment_id}", {
          params: { path: { document_id: documentId, attachment_id: attachmentId } },
        }),
      ),
    onSettled,
  });
}

/** Add a PDF to an imported invoice: its original when it has none, else an attachment. */
export function useAddFile(documentId: string) {
  const onChanged = useOnChanged();
  const client = useQueryClient();
  return useIdempotentMutation({
    mutationFn: (file: File, idempotent) => postFile(documentId, file, idempotent),
    onSuccess: (document) => {
      const before = client.getQueryData<DocumentDetail>(documentKeys.detail(documentId));
      onChanged(document);
      void client.invalidateQueries({ queryKey: attachmentsQuery(documentId).queryKey });
      // The original has just been added: show it.
      if (before?.has_pdf !== true) releaseDocumentPdf(client, documentId);
    },
  });
}
