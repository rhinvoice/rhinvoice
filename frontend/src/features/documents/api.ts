import { keepPreviousData, queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type components } from "@/api/client";
import { markItemsPaid } from "@/features/documents/paid-rows";

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
export type DocumentPage = components["schemas"]["DocumentPage"];
export type CurrencyTotals = components["schemas"]["CurrencyTotalsResponse"];
export type RecordedPayment = components["schemas"]["RecordedPaymentSchema"];

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

/** Store the changed document and refresh everything that summarises documents. */
function useOnChanged() {
  const client = useQueryClient();
  return (document: DocumentDetail) => {
    client.setQueryData(documentKeys.detail(document.id), document);
    void client.invalidateQueries({ queryKey: documentKeys.lists });
    void client.invalidateQueries({ queryKey: documentKeys.dashboard });
  };
}

export function useCreateDocument() {
  const onSuccess = useOnChanged();
  return useMutation({
    mutationFn: (body: CreateRequest) => unwrap(api.POST("/api/documents", { body })),
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

type Action = "issue" | "accept" | "decline" | "cancel" | "convert" | "duplicate";

const byId = (id: string) => ({ params: { path: { document_id: id } } });

const ACTIONS: Readonly<Record<Action, (id: string) => Promise<DocumentDetail>>> = {
  issue: (id) => unwrap(api.POST("/api/documents/{document_id}/issue", byId(id))),
  accept: (id) => unwrap(api.POST("/api/documents/{document_id}/accept", byId(id))),
  decline: (id) => unwrap(api.POST("/api/documents/{document_id}/decline", byId(id))),
  cancel: (id) => unwrap(api.POST("/api/documents/{document_id}/cancel", byId(id))),
  convert: (id) => unwrap(api.POST("/api/documents/{document_id}/convert", byId(id))),
  duplicate: (id) => unwrap(api.POST("/api/documents/{document_id}/duplicate", byId(id))),
};

/** Lifecycle actions without a body; "convert" and "duplicate" return the new draft. */
export function useDocumentAction(action: Action) {
  const onSuccess = useOnChanged();
  const client = useQueryClient();
  return useMutation({
    mutationFn: ACTIONS[action],
    onSuccess: (document, id) => {
      onSuccess(document);
      // The source changed too: a converted quote gets an event, a cancelled
      // invoice points to its cancellation.
      if (document.id !== id) void client.invalidateQueries({ queryKey: documentKeys.detail(id) });
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
  return useMutation({
    mutationFn: (payment: PaymentInput) =>
      unwrap(
        api.POST("/api/documents/{document_id}/payments", {
          params: { path: { document_id: id } },
          body: { paid_on: payment.paidOn, amount: payment.amount, note: payment.note },
        }),
      ),
    onSuccess,
  });
}

export function useMarkPaid(id: string) {
  const onSuccess = useOnChanged();
  return useMutation({
    mutationFn: (paidOn: string) =>
      unwrap(
        api.POST("/api/documents/{document_id}/mark-paid", {
          params: { path: { document_id: id } },
          body: { paid_on: paidOn },
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
  return useMutation({
    // Without a date the server uses today in the installation's time zone.
    mutationFn: (ids: readonly string[]) =>
      unwrap(api.POST("/api/documents/mark-paid", { body: { document_ids: [...ids] } })),
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
  return useMutation({
    mutationFn: (payments: readonly RecordedPayment[]) =>
      unwrap(api.POST("/api/documents/remove-payments", { body: { payments: [...payments] } })),
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
