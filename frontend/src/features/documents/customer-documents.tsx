import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { FileTextIcon, PlusIcon } from "lucide-react";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { documentListQuery } from "@/features/documents/api";
import { DocumentStatusBadge } from "@/features/shared/document-status";
import { formatDate, formatMoney } from "@/lib/format";

const HISTORY_SIZE = 20;

/** The newest documents of a customer, shown on the customer page. */
export function CustomerDocuments({ customerId }: { readonly customerId: string }) {
  const { t, locale } = useI18n();
  const query = useQuery(
    documentListQuery({
      types: ["quote", "invoice", "cancellation"],
      statuses: [],
      customerId,
      q: "",
      sort: "created_at",
      direction: "desc",
      offset: 0,
      limit: HISTORY_SIZE,
    }),
  );
  const items = query.data?.items;
  return (
    <Card className="h-fit" aria-labelledby="customer-documents">
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle id="customer-documents">{t("customers.documentsTitle")}</CardTitle>
        <div className="flex gap-2">
          <Button asChild size="sm">
            <Link to="/invoices/new" search={{ customer: customerId }}>
              <PlusIcon aria-hidden="true" />
              {t("documents.newInvoice")}
            </Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link to="/quotes/new" search={{ customer: customerId }}>
              <PlusIcon aria-hidden="true" />
              {t("documents.newQuote")}
            </Link>
          </Button>
        </div>
      </CardHeader>
      {items === undefined ? (
        <div className="flex flex-col gap-2" aria-busy="true" aria-label={t("app.loading")}>
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={FileTextIcon}
          title={t("customers.documentsTitle")}
          description={t("customers.documentsEmpty")}
        />
      ) : (
        <ul className="flex flex-col divide-y">
          {items.map((item) => (
            <li key={item.id} className="relative flex items-center justify-between gap-3 py-2">
              <div className="flex min-w-0 flex-col">
                <Link
                  to="/documents/$documentId"
                  params={{ documentId: item.id }}
                  className="inline-flex min-h-6 items-center text-sm font-medium underline-offset-4 after:absolute after:inset-0 hover:underline"
                >
                  {t(`documentType.${item.type}`)} {item.number ?? ""}
                </Link>
                <span className="truncate text-xs text-muted-foreground">
                  {item.issue_date === null ? item.subject : formatDate(item.issue_date, locale)}
                </span>
              </div>
              <div className="flex flex-col items-end gap-1">
                <span className="text-sm font-medium tabular-nums">
                  {formatMoney(item.total, item.currency, locale)}
                </span>
                <DocumentStatusBadge status={item.display_status} dueDate={item.due_date} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
