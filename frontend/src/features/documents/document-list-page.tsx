import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  BellRingIcon,
  CheckIcon,
  FileTextIcon,
  PlusIcon,
  ReceiptIcon,
  RepeatIcon,
  SearchIcon,
  UploadIcon,
  XIcon,
} from "lucide-react";
import { useEffect, useId, useState } from "react";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Kbd } from "@/components/ui/kbd";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import {
  SortableHead,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDebouncedValue } from "@/components/use-debounced-value";
import { useDocumentTitle } from "@/components/use-document-title";
import {
  documentListQuery,
  useMarkPaidMany,
  useRemovePayments,
  type DocumentPage,
  type DocumentSort,
  type DocumentSummary,
} from "@/features/documents/api";
import { BadDebtsCard } from "@/features/documents/bad-debts-card";
import { CustomerPicker } from "@/features/documents/customer-picker";
import {
  documentAriaSort,
  isPayable,
  toggleDocumentSort,
  viewCount,
  viewFilter,
  VIEWS,
  type DocumentListSearch,
  type ListKind,
} from "@/features/documents/document-list-search";
import { DocumentStatusBadge } from "@/features/shared/document-status";
import { FormAlert } from "@/features/shared/form-alert";
import { PAGE_SIZE } from "@/features/shared/list-search";
import { Pagination } from "@/features/shared/pagination";
import { showUndoToast } from "@/features/shared/undo";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { cn } from "@/lib/cn";
import { ApiError } from "@/lib/api-error";
import { addDecimals } from "@/lib/decimal";
import { formatDate, formatMoney } from "@/lib/format";

interface DocumentListPageProps {
  readonly kind: ListKind;
  readonly search: DocumentListSearch;
  readonly onSearchChange: (update: Partial<DocumentListSearch>) => void;
}

const NO_SELECTION: ReadonlyMap<string, DocumentSummary> = new Map();

export function DocumentListPage({ kind, search, onSearchChange }: DocumentListPageProps) {
  const { t } = useI18n();
  const title = kind === "invoice" ? t("nav.invoices") : t("nav.quotes");
  useDocumentTitle(t("app.pageTitle", { title }));
  const errorMessage = useErrorMessage();
  const [term, setTerm] = useState(search.q);
  const debounced = useDebouncedValue(term, 250);
  useEffect(() => {
    if (debounced !== search.q) onSearchChange({ q: debounced, page: 1 });
  }, [debounced, search.q, onSearchChange]);

  const offset = (search.page - 1) * PAGE_SIZE;
  const filter = viewFilter(kind, search.view);
  const query = useQuery(
    documentListQuery({
      ...filter,
      q: search.q,
      ...(search.year === "all" ? {} : { year: search.year }),
      ...(search.customer === "" ? {} : { customerId: search.customer }),
      sort: search.sort,
      direction: search.dir,
      offset,
      limit: PAGE_SIZE,
    }),
  );
  const data = query.data;

  // The selection belongs to the rows it was made on: another filter or page starts empty.
  const selectionKey = JSON.stringify([kind, search]);
  const [selection, setSelection] = useState({ key: selectionKey, items: NO_SELECTION });
  const selected = selection.key === selectionKey ? selection.items : NO_SELECTION;
  const select = (items: ReadonlyMap<string, DocumentSummary>) => {
    setSelection({ key: selectionKey, items });
  };

  const markPaid = useMarkPaidMany();
  const removePayments = useRemovePayments();
  const fail = (caught: unknown, paying: readonly DocumentSummary[] = []) => {
    // The server names the invoice that stopped a bulk payment.
    const blocking =
      caught instanceof ApiError && caught.code === "cannot_mark_paid"
        ? caught.details["document"]
        : undefined;
    const message =
      blocking === undefined
        ? errorMessage(caught)
        : t("documents.cannotMarkPaid", {
            number: paying.find((item) => item.id === blocking)?.number ?? blocking,
          });
    toast.error(message ?? t("error.generic"), { duration: Infinity });
  };
  const pay = (documents: readonly DocumentSummary[]) => {
    markPaid.mutate(
      documents.map((document) => document.id),
      {
        onSuccess: (result) => {
          select(NO_SELECTION);
          const [only] = documents;
          const message =
            documents.length === 1 && only !== undefined
              ? t("documents.markedPaidNumber", { number: only.number ?? "" })
              : t("documents.markedPaidMany", { count: documents.length });
          showUndoToast(message, t("common.undo"), () => {
            removePayments.mutate(result.payments, {
              onSuccess: () => toast.success(t("documents.paymentsUndone")),
              onError: (caught) => {
                fail(caught);
              },
            });
          });
        },
        onError: (caught) => {
          fail(caught, documents);
        },
      },
    );
  };

  const filtered =
    search.q !== "" || search.view !== "all" || search.year !== "all" || search.customer !== "";
  const newPath = kind === "invoice" ? "/invoices/new" : "/quotes/new";
  const newLabel = kind === "invoice" ? t("documents.newInvoice") : t("documents.newQuote");

  const newButton = (
    <Button asChild>
      <Link to={newPath}>
        <PlusIcon aria-hidden="true" />
        {newLabel}
        <Kbd className="border-transparent bg-primary-foreground/15 text-primary-foreground">
          {kind === "invoice" ? "N" : "Q"}
        </Kbd>
      </Link>
    </Button>
  );

  return (
    <>
      <PageHeader
        title={title}
        actions={
          kind === "invoice" ? (
            <div className="flex flex-wrap gap-2">
              <Button asChild variant="outline">
                <Link to="/dunning">
                  <BellRingIcon aria-hidden="true" />
                  {t("dunning.title")}
                </Link>
              </Button>
              <Button asChild variant="outline">
                <Link to="/recurring">
                  <RepeatIcon aria-hidden="true" />
                  {t("recurring.short")}
                </Link>
              </Button>
              <Button asChild variant="outline">
                <Link to="/invoices/import">
                  <UploadIcon aria-hidden="true" />
                  {t("import.open")}
                </Link>
              </Button>
              {newButton}
            </div>
          ) : (
            newButton
          )
        }
      />
      <Filters
        kind={kind}
        search={search}
        term={term}
        onTermChange={setTerm}
        data={data}
        onSearchChange={onSearchChange}
      />

      <FormAlert message={query.isError ? errorMessage(query.error) : null} />

      {data === undefined && query.isPending ? (
        <div className="flex flex-col gap-2" aria-busy="true" aria-label={t("app.loading")}>
          {Array.from({ length: 5 }, (_, index) => (
            <Skeleton key={index} className="h-11 w-full" />
          ))}
        </div>
      ) : data?.total === 0 ? (
        filtered ? (
          <EmptyState
            icon={SearchIcon}
            title={t("documents.noResults")}
            description={search.q === "" ? t(`documents.view.${search.view}`) : search.q}
            action={
              <Button
                variant="outline"
                onClick={() => {
                  setTerm("");
                  onSearchChange({ q: "", view: "all", year: "all", customer: "", page: 1 });
                }}
              >
                {t("documents.resetFilter")}
              </Button>
            }
          />
        ) : (
          <EmptyState
            icon={kind === "invoice" ? ReceiptIcon : FileTextIcon}
            title={kind === "invoice" ? t("documents.emptyInvoices") : t("documents.emptyQuotes")}
            description={
              kind === "invoice"
                ? t("documents.emptyInvoicesDescription")
                : t("documents.emptyQuotesDescription")
            }
            action={newButton}
          />
        )
      ) : data !== undefined ? (
        <>
          <DocumentTable
            kind={kind}
            search={search}
            items={data.items}
            selected={selected}
            onSelect={select}
            onPay={pay}
            paying={markPaid.isPending}
            onSearchChange={onSearchChange}
          />
          <Totals kind={kind} data={data} />
          <Pagination
            offset={offset}
            limit={PAGE_SIZE}
            total={data.total}
            onChange={(nextOffset) => {
              onSearchChange({ page: nextOffset / PAGE_SIZE + 1 });
            }}
          />
        </>
      ) : null}

      {kind === "invoice" && search.view === "written_off" ? (
        <BadDebtsCard year={search.year} />
      ) : null}

      {selected.size > 0 ? (
        <SelectionBar
          selected={[...selected.values()]}
          paying={markPaid.isPending}
          onPay={pay}
          onClear={() => {
            select(NO_SELECTION);
          }}
        />
      ) : null}
    </>
  );
}

interface FiltersProps {
  readonly kind: ListKind;
  readonly search: DocumentListSearch;
  readonly term: string;
  readonly onTermChange: (term: string) => void;
  readonly data: DocumentPage | undefined;
  readonly onSearchChange: (update: Partial<DocumentListSearch>) => void;
}

function Filters({ kind, search, term, onTermChange, data, onSearchChange }: FiltersProps) {
  const { t } = useI18n();
  const id = useId();
  const years = data?.years ?? [];
  // A year from the address bar stays selectable even without documents.
  const yearOptions =
    search.year === "all" || years.includes(search.year) ? years : [search.year, ...years];
  return (
    <div role="search" aria-label={t("documents.filters")} className="flex flex-col gap-3">
      <div className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center">
        <div className="relative w-full md:max-w-xs">
          <Label htmlFor={`${id}-search`} className="sr-only">
            {t("documents.searchLabel")}
          </Label>
          <SearchIcon
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            id={`${id}-search`}
            type="search"
            data-page-search
            className="pl-9"
            placeholder={t("documents.searchPlaceholder")}
            value={term}
            onChange={(event) => {
              onTermChange(event.target.value);
            }}
          />
        </div>
        <div className="w-full md:w-40">
          <Label htmlFor={`${id}-year`} className="sr-only">
            {t("documents.year")}
          </Label>
          <NativeSelect
            id={`${id}-year`}
            value={String(search.year)}
            onChange={(event) => {
              const value = event.target.value;
              onSearchChange({ year: value === "all" ? "all" : Number(value), page: 1 });
            }}
          >
            <option value="all">{t("documents.allYears")}</option>
            {yearOptions.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="flex w-full items-center gap-1 md:w-72">
          <Label htmlFor={`${id}-customer`} className="sr-only">
            {t("documents.customerFilter")}
          </Label>
          <div className="min-w-0 flex-1">
            <CustomerPicker
              id={`${id}-customer`}
              value={search.customer}
              placeholder={t("documents.allCustomers")}
              onChange={(customer) => {
                onSearchChange({ customer: customer.id, page: 1 });
              }}
            />
          </div>
          {search.customer === "" ? null : (
            <Button
              variant="ghost"
              size="icon"
              aria-label={t("documents.removeCustomerFilter")}
              onClick={() => {
                onSearchChange({ customer: "", page: 1 });
              }}
            >
              <XIcon aria-hidden="true" />
            </Button>
          )}
        </div>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div role="group" aria-label={t("documents.views")} className="flex flex-wrap gap-1.5">
          {VIEWS[kind].map((view) => {
            const count =
              data === undefined ? undefined : viewCount(kind, view, data.status_counts);
            const active = search.view === view;
            return (
              <Button
                key={view}
                size="sm"
                variant={active ? "secondary" : "ghost"}
                className={cn("rounded-full", active && "bg-accent text-accent-foreground")}
                aria-pressed={active}
                onClick={() => {
                  onSearchChange({ view, page: 1 });
                }}
              >
                {t(`documents.view.${view}`)}
                {count === undefined ? null : (
                  <span
                    className={cn(
                      "tabular-nums",
                      active ? "text-accent-foreground" : "text-muted-foreground",
                    )}
                  >
                    {count}
                  </span>
                )}
              </Button>
            );
          })}
        </div>
        <p className="text-sm text-muted-foreground sm:ml-auto" aria-live="polite">
          {data === undefined ? "" : t("common.results", { count: data.total })}
        </p>
      </div>
    </div>
  );
}

interface DocumentTableProps {
  readonly kind: ListKind;
  readonly search: DocumentListSearch;
  readonly items: readonly DocumentSummary[];
  readonly selected: ReadonlyMap<string, DocumentSummary>;
  readonly onSelect: (items: ReadonlyMap<string, DocumentSummary>) => void;
  readonly onPay: (documents: readonly DocumentSummary[]) => void;
  readonly paying: boolean;
  readonly onSearchChange: (update: Partial<DocumentListSearch>) => void;
}

function DocumentTable({
  kind,
  search,
  items,
  selected,
  onSelect,
  onPay,
  paying,
  onSearchChange,
}: DocumentTableProps) {
  const { t, locale } = useI18n();
  const invoices = kind === "invoice";
  const payable = items.filter(isPayable);
  const allSelected = payable.length > 0 && payable.every((item) => selected.has(item.id));

  const toggle = (item: DocumentSummary, checked: boolean) => {
    const next = new Map(selected);
    if (checked) next.set(item.id, item);
    else next.delete(item.id);
    onSelect(next);
  };

  const sortHead = (sort: DocumentSort, label: string, className?: string) => (
    <SortableHead
      {...(className === undefined ? {} : { className })}
      state={documentAriaSort(search, sort)}
      onSort={() => {
        onSearchChange(toggleDocumentSort(search, sort));
      }}
    >
      {label}
    </SortableHead>
  );

  return (
    <Table>
      <TableHeader>
        <TableRow>
          {invoices ? (
            <TableHead className="hidden w-10 pr-0 sm:table-cell">
              <SelectBox
                label={t("documents.selectAllPayable")}
                checked={allSelected}
                disabled={payable.length === 0}
                onChange={(checked) => {
                  const next = new Map(selected);
                  for (const item of payable) {
                    if (checked) next.set(item.id, item);
                    else next.delete(item.id);
                  }
                  onSelect(next);
                }}
              />
            </TableHead>
          ) : null}
          <TableHead className="hidden w-40 sm:table-cell">{t("documents.status")}</TableHead>
          {sortHead("number", t("documents.number"), "w-36")}
          {sortHead("customer", t("documents.customer"), "hidden min-w-44 sm:table-cell")}
          {/* A column of its own only where the sidebar leaves room for it. */}
          <TableHead className="hidden 2xl:table-cell">{t("documents.subject")}</TableHead>
          {sortHead("issue_date", t("documents.issueDate"), "hidden md:table-cell")}
          {sortHead(
            "due_date",
            invoices ? t("documents.dueDate") : t("documents.validUntil"),
            "hidden lg:table-cell",
          )}
          {sortHead("total", t("documents.amount"), "text-right")}
          {invoices ? (
            <TableHead className="hidden w-px sm:table-cell">
              <span className="sr-only">{t("documents.lineActions")}</span>
            </TableHead>
          ) : null}
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => {
          const cancelled = item.display_status === "cancelled";
          const label = item.number ?? t("status.draft");
          const canPay = isPayable(item);
          const payButton = (
            <Button
              variant="outline"
              size="sm"
              disabled={paying}
              aria-label={t("documents.markPaidRow", { number: label })}
              onClick={() => {
                onPay([item]);
              }}
            >
              <CheckIcon aria-hidden="true" />
              {t("documents.markPaidShort")}
            </Button>
          );
          return (
            <TableRow
              key={item.id}
              className={cn("relative", selected.has(item.id) && "bg-accent/60")}
            >
              {invoices ? (
                <TableCell className="relative z-10 hidden pr-0 sm:table-cell">
                  {canPay ? (
                    <SelectBox
                      label={t("documents.selectDocument", { number: label })}
                      checked={selected.has(item.id)}
                      onChange={(checked) => {
                        toggle(item, checked);
                      }}
                    />
                  ) : null}
                </TableCell>
              ) : null}
              <TableCell className="hidden sm:table-cell">
                <DocumentStatusBadge status={item.display_status} dueDate={item.due_date} />
              </TableCell>
              <TableCell className="tabular-nums">
                {/* The link covers the row, so the whole row is clickable. */}
                <Link
                  to="/documents/$documentId"
                  params={{ documentId: item.id }}
                  className="inline-flex min-h-6 items-center font-medium underline-offset-4 after:absolute after:inset-0 hover:underline"
                >
                  {item.number ?? (
                    <span className="text-muted-foreground">{t("status.draft")}</span>
                  )}
                </Link>
                {item.type === "cancellation" ? (
                  <span className="block text-xs text-muted-foreground">
                    {t("documentType.cancellation")}
                  </span>
                ) : null}
                {item.imported ? (
                  <span className="block text-xs text-muted-foreground">
                    {t("documents.imported")}
                  </span>
                ) : null}
                {/* Phones show one compact cell instead of the customer and status columns. */}
                <span className="block text-sm sm:hidden">{item.customer_name}</span>
                <span className="mt-1 block sm:hidden">
                  <DocumentStatusBadge status={item.display_status} dueDate={item.due_date} />
                </span>
              </TableCell>
              <TableCell className="hidden sm:table-cell">
                <span className="font-medium">{item.customer_name}</span>
                <span className="block text-xs text-muted-foreground 2xl:hidden">
                  {item.subject}
                </span>
              </TableCell>
              <TableCell className="hidden max-w-64 truncate 2xl:table-cell">
                {item.subject}
              </TableCell>
              <TableCell className="hidden tabular-nums md:table-cell">
                {item.issue_date === null ? "" : formatDate(item.issue_date, locale)}
              </TableCell>
              <TableCell className="hidden tabular-nums lg:table-cell">
                {item.due_date === null ? "" : formatDate(item.due_date, locale)}
              </TableCell>
              <TableCell
                className={cn(
                  "text-right font-medium whitespace-nowrap tabular-nums",
                  cancelled && "text-muted-foreground line-through",
                )}
              >
                {formatMoney(item.total, item.currency, locale)}
                {item.display_status === "partially_paid" ||
                (item.display_status === "overdue" && item.open_amount !== item.total) ? (
                  <span className="block text-xs font-normal text-muted-foreground">
                    {t("documents.openShort", {
                      amount: formatMoney(item.open_amount, item.currency, locale),
                    })}
                  </span>
                ) : null}
                {canPay ? (
                  <span className="relative z-10 mt-1 block sm:hidden">{payButton}</span>
                ) : null}
              </TableCell>
              {invoices ? (
                <TableCell className="relative z-10 hidden text-right sm:table-cell">
                  {canPay ? payButton : null}
                </TableCell>
              ) : null}
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

interface SelectBoxProps {
  readonly label: string;
  readonly checked: boolean;
  readonly disabled?: boolean;
  readonly onChange: (checked: boolean) => void;
}

/** A row checkbox with a 24 × 24 px target (WCAG 2.5.8). */
function SelectBox({ label, checked, disabled = false, onChange }: SelectBoxProps) {
  return (
    <label className="flex size-6 cursor-pointer items-center justify-center has-disabled:cursor-not-allowed">
      <input
        type="checkbox"
        className="size-4 accent-primary"
        aria-label={label}
        checked={checked}
        disabled={disabled}
        onChange={(event) => {
          onChange(event.target.checked);
        }}
      />
    </label>
  );
}

/** Sums of the whole selection (all pages), one line per currency. */
function Totals({ kind, data }: { readonly kind: ListKind; readonly data: DocumentPage }) {
  const { t, locale } = useI18n();
  if (data.totals.length === 0) return null;
  return (
    <section
      aria-label={t("documents.sums")}
      className="flex flex-col items-end gap-1 px-1 text-sm text-muted-foreground"
    >
      {data.totals.map((sum) => (
        <p key={sum.currency} className="flex flex-wrap justify-end gap-x-4 tabular-nums">
          <span>
            {t(kind === "invoice" ? "documents.sumCountInvoices" : "documents.sumCountQuotes", {
              count: sum.count,
              currency: sum.currency,
            })}
          </span>
          <span className="font-medium text-foreground">
            {t("documents.sumTotal", { amount: formatMoney(sum.total, sum.currency, locale) })}
          </span>
          {kind === "invoice" ? (
            <span>
              {t("documents.sumOpen", { amount: formatMoney(sum.open, sum.currency, locale) })}
            </span>
          ) : null}
        </p>
      ))}
    </section>
  );
}

interface SelectionBarProps {
  readonly selected: readonly DocumentSummary[];
  readonly paying: boolean;
  readonly onPay: (documents: readonly DocumentSummary[]) => void;
  readonly onClear: () => void;
}

function SelectionBar({ selected, paying, onPay, onClear }: SelectionBarProps) {
  const { t, locale } = useI18n();
  const currencies = [...new Set(selected.map((item) => item.currency))].sort();
  return (
    <section
      aria-label={t("documents.selection")}
      className="fixed inset-x-4 bottom-[calc(var(--bottombar-height)+0.75rem)] z-30 mx-auto flex w-fit max-w-[calc(100vw-2rem)] flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl bg-foreground py-2 pr-2 pl-5 text-sm text-background shadow-lg md:bottom-6"
    >
      <p aria-live="polite" className="tabular-nums">
        <span className="font-semibold">
          {t("documents.selectedCount", { count: selected.length })}
        </span>
        {" · "}
        {currencies
          .map((currency) =>
            formatMoney(
              addDecimals(
                selected
                  .filter((item) => item.currency === currency)
                  .map((item) => item.open_amount),
              ),
              currency,
              locale,
            ),
          )
          .join(" + ")}
      </p>
      <div className="flex gap-1">
        <Button
          size="sm"
          disabled={paying}
          className="bg-background text-foreground hover:bg-background/90"
          onClick={() => {
            onPay(selected);
          }}
        >
          <CheckIcon aria-hidden="true" />
          {t("documents.markSelectedPaid")}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="text-background hover:bg-background/15 hover:text-background"
          onClick={onClear}
        >
          {t("documents.clearSelection")}
        </Button>
      </div>
    </section>
  );
}
