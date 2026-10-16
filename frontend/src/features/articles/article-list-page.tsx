import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { ArchiveIcon, PackageIcon, PlusIcon, SearchIcon, UploadIcon } from "lucide-react";
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
import { usePageShortcut } from "@/components/use-key-shortcuts";
import { priceCurrencies } from "@/features/articles/article-form-model";
import { articleListQuery, type ArticleSort } from "@/features/articles/api";
import { companyQuery } from "@/features/shared/company-api";
import { ariaSort, PAGE_SIZE, toggleSort, type ListSearch } from "@/features/shared/list-search";
import { Pagination } from "@/features/shared/pagination";
import { FormAlert } from "@/features/shared/form-alert";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { cn } from "@/lib/cn";
import { formatMoney } from "@/lib/format";
import { germanOrEnglish } from "@/lib/locale";

interface ArticleListPageProps {
  readonly search: ListSearch<ArticleSort>;
  readonly onSearchChange: (update: Partial<ListSearch<ArticleSort>>) => void;
}

export function ArticleListPage({ search, onSearchChange }: ArticleListPageProps) {
  const { t, locale } = useI18n();
  useDocumentTitle(t("app.pageTitle", { title: t("articles.title") }));
  const navigate = useNavigate();
  const errorMessage = useErrorMessage();
  // The company's currency first; on narrow screens only that one.
  const currencies = priceCurrencies(useQuery(companyQuery).data?.default_currency);
  const [term, setTerm] = useState(search.q);
  const debounced = useDebouncedValue(term, 250);
  useEffect(() => {
    if (debounced !== search.q) onSearchChange({ q: debounced, page: 1 });
  }, [debounced, search.q, onSearchChange]);
  usePageShortcut("a", () => void navigate({ to: "/articles/new" }));

  const offset = (search.page - 1) * PAGE_SIZE;
  const query = useQuery(
    articleListQuery({
      q: search.q,
      includeArchived: search.archived,
      sort: search.sort,
      direction: search.dir,
      offset,
      limit: PAGE_SIZE,
    }),
  );
  const data = query.data;
  const filtered = search.q !== "" || search.archived;

  const newButton = (
    <Button asChild>
      <Link to="/articles/new">
        <PlusIcon aria-hidden="true" />
        {t("articles.new")}
        <Kbd className="border-transparent bg-primary-foreground/15 text-primary-foreground">C</Kbd>
      </Link>
    </Button>
  );

  return (
    <>
      <PageHeader
        title={t("articles.title")}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline">
              <Link to="/articles/import">
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
          <Label htmlFor="article-search" className="sr-only">
            {t("articles.searchLabel")}
          </Label>
          <SearchIcon
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            id="article-search"
            type="search"
            data-page-search
            className="pl-9"
            placeholder={t("articles.searchPlaceholder")}
            value={term}
            onChange={(event) => {
              setTerm(event.target.value);
            }}
          />
        </div>
        <div className="flex items-center gap-2">
          <Switch
            id="article-archived"
            checked={search.archived}
            onCheckedChange={(archived) => {
              onSearchChange({ archived, page: 1 });
            }}
          />
          <Label htmlFor="article-archived">{t("common.showArchived")}</Label>
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
            title={t("articles.noResults")}
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
            icon={PackageIcon}
            title={t("articles.emptyTitle")}
            description={t("articles.emptyDescription")}
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
                  {t("articles.number")}
                </SortableHead>
                <SortableHead
                  state={ariaSort(search, "name")}
                  onSort={() => {
                    onSearchChange(toggleSort(search, "name"));
                  }}
                >
                  {t("articles.name")}
                </SortableHead>
                <SortableHead
                  className="hidden md:table-cell"
                  state={ariaSort(search, "group")}
                  onSort={() => {
                    onSearchChange(toggleSort(search, "group"));
                  }}
                >
                  {t("articles.group")}
                </SortableHead>
                <TableHead className="hidden sm:table-cell">{t("articles.unit")}</TableHead>
                {currencies.map((currency, index) => (
                  <TableHead
                    key={currency}
                    className={index === 0 ? "text-right" : "hidden text-right sm:table-cell"}
                  >
                    {currency}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((article) => (
                <TableRow key={article.id}>
                  <TableCell className="text-muted-foreground tabular-nums">
                    {article.number}
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        to="/articles/$articleId"
                        params={{ articleId: article.id }}
                        className="inline-flex min-h-6 items-center font-medium underline-offset-4 hover:underline"
                      >
                        {article.name}
                      </Link>
                      {article.archived ? (
                        <Badge>
                          <ArchiveIcon aria-hidden="true" />
                          {t("common.archived")}
                        </Badge>
                      ) : null}
                    </div>
                  </TableCell>
                  <TableCell className="hidden md:table-cell">{article.group}</TableCell>
                  <TableCell className="hidden sm:table-cell">
                    {germanOrEnglish(locale, article.unit_label_de, article.unit_label_en)}
                  </TableCell>
                  {currencies.map((currency, index) => {
                    const price = article.prices[currency];
                    return (
                      <TableCell
                        key={currency}
                        className={cn(
                          "text-right whitespace-nowrap tabular-nums",
                          index > 0 && "hidden sm:table-cell",
                        )}
                      >
                        {price === undefined ? "" : formatMoney(price, currency, locale, 4)}
                      </TableCell>
                    );
                  })}
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
