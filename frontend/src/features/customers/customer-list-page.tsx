import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArchiveIcon, PlusIcon, SearchIcon, UsersIcon, UploadIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { useI18n } from "@/components/i18n/use-i18n";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Kbd } from "@/components/ui/kbd";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
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
import { customerListQuery, type CustomerSort } from "@/features/customers/api";
import { ariaSort, PAGE_SIZE, toggleSort, type ListSearch } from "@/features/shared/list-search";
import { Pagination } from "@/features/shared/pagination";
import { companyQuery } from "@/features/shared/company-api";
import { FormAlert } from "@/features/shared/form-alert";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { countryName } from "@/lib/countries";

interface CustomerListPageProps {
  readonly search: ListSearch<CustomerSort>;
  readonly onSearchChange: (update: Partial<ListSearch<CustomerSort>>) => void;
}

export function CustomerListPage({ search, onSearchChange }: CustomerListPageProps) {
  const { t, locale } = useI18n();
  useDocumentTitle(t("app.pageTitle", { title: t("customers.title") }));
  const errorMessage = useErrorMessage();
  const [term, setTerm] = useState(search.q);
  const debounced = useDebouncedValue(term, 250);
  useEffect(() => {
    if (debounced !== search.q) onSearchChange({ q: debounced, page: 1 });
  }, [debounced, search.q, onSearchChange]);

  const offset = (search.page - 1) * PAGE_SIZE;
  const query = useQuery(
    customerListQuery({
      q: search.q,
      includeArchived: search.archived,
      sort: search.sort,
      direction: search.dir,
      offset,
      limit: PAGE_SIZE,
    }),
  );
  const data = query.data;
  // Only foreign countries are named, relative to the company's country.
  const homeCountry = useQuery(companyQuery).data?.country ?? "CH";
  const filtered = search.q !== "" || search.archived;

  const newButton = (
    <Button asChild>
      <Link to="/customers/new">
        <PlusIcon aria-hidden="true" />
        {t("customers.new")}
        <Kbd className="border-transparent bg-primary-foreground/15 text-primary-foreground">C</Kbd>
      </Link>
    </Button>
  );

  return (
    <>
      <PageHeader
        title={t("customers.title")}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline">
              <Link to="/customers/import">
                <UploadIcon aria-hidden="true" />
                {t("import.open")}
              </Link>
            </Button>
            {newButton}
          </div>
        }
      />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative w-full sm:max-w-sm">
          <Label htmlFor="customer-search" className="sr-only">
            {t("customers.searchLabel")}
          </Label>
          <SearchIcon
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            id="customer-search"
            type="search"
            data-page-search
            className="pl-9"
            placeholder={t("customers.searchPlaceholder")}
            value={term}
            onChange={(event) => {
              setTerm(event.target.value);
            }}
          />
        </div>
        <div className="flex items-center gap-2">
          <Switch
            id="customer-archived"
            checked={search.archived}
            onCheckedChange={(archived) => {
              onSearchChange({ archived, page: 1 });
            }}
          />
          <Label htmlFor="customer-archived">{t("common.showArchived")}</Label>
        </div>
        <p className="text-sm text-muted-foreground sm:ml-auto" aria-live="polite">
          {data === undefined ? "" : t("common.results", { count: data.total })}
        </p>
      </div>

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
            title={t("customers.noResults")}
            description={search.q}
            action={
              <Button
                variant="outline"
                onClick={() => {
                  setTerm("");
                  onSearchChange({ q: "", archived: false, page: 1 });
                }}
              >
                {t("customers.resetSearch")}
              </Button>
            }
          />
        ) : (
          <EmptyState
            icon={UsersIcon}
            title={t("customers.emptyTitle")}
            description={t("customers.emptyDescription")}
            action={newButton}
          />
        )
      ) : data !== undefined ? (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <SortableHead
                  className="w-24"
                  state={ariaSort(search, "number")}
                  onSort={() => {
                    onSearchChange(toggleSort(search, "number"));
                  }}
                >
                  {t("customers.number")}
                </SortableHead>
                <SortableHead
                  state={ariaSort(search, "name")}
                  onSort={() => {
                    onSearchChange(toggleSort(search, "name"));
                  }}
                >
                  {t("customers.name")}
                </SortableHead>
                <SortableHead
                  className="hidden md:table-cell"
                  state={ariaSort(search, "city")}
                  onSort={() => {
                    onSearchChange(toggleSort(search, "city"));
                  }}
                >
                  {t("customers.city")}
                </SortableHead>
                <TableHead className="hidden lg:table-cell">{t("customers.email")}</TableHead>
                <TableHead className="hidden lg:table-cell">{t("customers.group")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((customer) => (
                <TableRow key={customer.id}>
                  <TableCell className="text-muted-foreground tabular-nums">
                    {customer.number}
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        to="/customers/$customerId"
                        params={{ customerId: customer.id }}
                        className="inline-flex min-h-6 items-center font-medium underline-offset-4 hover:underline"
                      >
                        {customer.display_name}
                      </Link>
                      {customer.archived ? (
                        <Badge>
                          <ArchiveIcon aria-hidden="true" />
                          {t("common.archived")}
                        </Badge>
                      ) : null}
                    </div>
                    <span className="text-xs text-muted-foreground md:hidden">
                      {customer.address.postal_code} {customer.address.city}
                    </span>
                  </TableCell>
                  <TableCell className="hidden md:table-cell">
                    {customer.address.postal_code} {customer.address.city}
                    {customer.address.country === homeCountry ? null : (
                      <span className="text-muted-foreground">
                        , {countryName(customer.address.country, locale)}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="hidden lg:table-cell">{customer.email ?? ""}</TableCell>
                  <TableCell className="hidden lg:table-cell">{customer.group}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
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
    </>
  );
}
