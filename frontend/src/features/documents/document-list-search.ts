import type {
  DisplayStatus,
  DocumentSort,
  DocumentSummary,
  DocumentType,
} from "@/features/documents/api";

export type ListKind = "invoice" | "quote";

/** Saved views of the lists (principles.md 4.3), stored in the URL as "view". */
export const VIEWS = {
  invoice: ["all", "draft", "open", "overdue", "paid", "cancelled"],
  quote: ["all", "draft", "sent", "accepted", "declined", "expired"],
} as const;

export type InvoiceView = (typeof VIEWS.invoice)[number];
export type QuoteView = (typeof VIEWS.quote)[number];
export type DocumentView = InvoiceView | QuoteView;

export const DOCUMENT_SORTS = [
  "created_at",
  "number",
  "issue_date",
  "due_date",
  "customer",
  "total",
] as const satisfies readonly DocumentSort[];

export interface DocumentListSearch {
  readonly q: string;
  readonly view: DocumentView;
  /** Calendar year of the document date, or "all". */
  readonly year: number | "all";
  /** Id of the customer to show, or "" for all customers. */
  readonly customer: string;
  readonly sort: DocumentSort;
  readonly dir: "asc" | "desc";
  readonly page: number;
}

export const DOCUMENT_LIST_DEFAULTS = {
  q: "",
  view: "all",
  year: "all",
  customer: "",
  sort: "created_at",
  dir: "desc",
  page: 1,
} as const satisfies DocumentListSearch;

// The range the API accepts.
const MIN_YEAR = 1900;
const MAX_YEAR = 9999;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function parseDocumentListSearch(
  raw: Record<string, unknown>,
  kind: ListKind,
): DocumentListSearch {
  const views: readonly string[] = VIEWS[kind];
  const view = typeof raw["view"] === "string" && views.includes(raw["view"]) ? raw["view"] : "all";
  const sort = DOCUMENT_SORTS.find((candidate) => candidate === raw["sort"]) ?? "created_at";
  const pageNumber = Number(raw["page"]);
  const year = Number(raw["year"]);
  const customer = raw["customer"];
  return {
    q: typeof raw["q"] === "string" ? raw["q"].slice(0, 100) : "",
    view: view as DocumentView,
    year: Number.isInteger(year) && year >= MIN_YEAR && year <= MAX_YEAR ? year : "all",
    customer: typeof customer === "string" && UUID.test(customer) ? customer.toLowerCase() : "",
    sort,
    dir: raw["dir"] === "asc" ? "asc" : "desc",
    page: Number.isInteger(pageNumber) && pageNumber > 1 ? pageNumber : 1,
  };
}

/** Document types and statuses that a view shows. */
export function viewFilter(
  kind: ListKind,
  view: DocumentView,
): { readonly types: DocumentType[]; readonly statuses: DisplayStatus[] } {
  if (kind === "quote") {
    return { types: ["quote"], statuses: view === "all" ? [] : [view as DisplayStatus] };
  }
  if (view === "all") {
    // Cancellation invoices belong to the invoices they cancel.
    return { types: ["invoice", "cancellation"], statuses: [] };
  }
  if (view === "open") {
    return { types: ["invoice"], statuses: ["issued", "partially_paid", "overdue"] };
  }
  return { types: ["invoice"], statuses: [view] };
}

/** Clicking a header sorts by it; clicking it again flips the direction. */
export function toggleDocumentSort(
  current: DocumentListSearch,
  sort: DocumentSort,
): Pick<DocumentListSearch, "sort" | "dir" | "page"> {
  if (current.sort === sort) return { sort, dir: current.dir === "asc" ? "desc" : "asc", page: 1 };
  // Text sorts start A–Z, dates and amounts newest/largest first.
  return { sort, dir: sort === "customer" || sort === "number" ? "asc" : "desc", page: 1 };
}

export function documentAriaSort(
  current: DocumentListSearch,
  sort: DocumentSort,
): "ascending" | "descending" | "none" {
  if (current.sort !== sort) return "none";
  return current.dir === "asc" ? "ascending" : "descending";
}

/** Number of documents a view shows, from the counts per status; undefined for "all". */
export function viewCount(
  kind: ListKind,
  view: DocumentView,
  counts: readonly { readonly status: DisplayStatus; readonly count: number }[],
): number | undefined {
  if (view === "all") return undefined;
  const statuses = viewFilter(kind, view).statuses;
  return counts
    .filter((entry) => statuses.includes(entry.status))
    .reduce((sum, entry) => sum + entry.count, 0);
}

/** Invoices that can be marked as paid straight from the list. */
export function isPayable(document: Pick<DocumentSummary, "type" | "display_status">): boolean {
  return (
    document.type === "invoice" &&
    (document.display_status === "issued" ||
      document.display_status === "partially_paid" ||
      document.display_status === "overdue")
  );
}
