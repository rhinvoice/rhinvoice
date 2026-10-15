import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { BellRingIcon, CircleCheckIcon, FileTextIcon, MailIcon } from "lucide-react";
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
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDocumentTitle } from "@/components/use-document-title";
import {
  dunningQuery,
  reminderPdfUrl,
  useWriteReminder,
  type DunningItem,
} from "@/features/dunning/api";
import { BackLink } from "@/features/shared/back-link";
import { FormAlert } from "@/features/shared/form-alert";
import { SendMailDialog } from "@/features/shared/send-mail-dialog";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { formatDate, formatMoney } from "@/lib/format";

/** Overdue invoices with their reminders and the next step. */
export function DunningPage() {
  const { t } = useI18n();
  useDocumentTitle(t("app.pageTitle", { title: t("dunning.title") }));
  const errorMessage = useErrorMessage();
  const query = useQuery(dunningQuery);
  const items = query.data;
  return (
    <>
      <BackLink to="/invoices" label={t("nav.invoices")} />
      <PageHeader
        title={t("dunning.title")}
        description={t("dunning.description")}
        actions={
          <Button asChild variant="outline">
            <Link to="/settings" search={{ tab: "dunning" }}>
              {t("dunning.settings")}
            </Link>
          </Button>
        }
      />
      <FormAlert message={query.isError ? errorMessage(query.error) : null} />
      {items === undefined ? (
        query.isPending ? (
          <Skeleton className="h-64" />
        ) : null
      ) : items.length === 0 ? (
        <EmptyState
          icon={CircleCheckIcon}
          title={t("dunning.emptyTitle")}
          description={t("dunning.emptyDescription")}
        />
      ) : (
        <Table scrollLabel={t("dunning.table")}>
          <caption className="sr-only">{t("dunning.table")}</caption>
          <TableHeader>
            <TableRow>
              <TableHead>{t("dunning.invoice")}</TableHead>
              <TableHead>{t("dunning.customer")}</TableHead>
              <TableHead className="text-right">{t("dunning.open")}</TableHead>
              <TableHead>{t("dunning.overdue")}</TableHead>
              <TableHead>{t("dunning.reminders")}</TableHead>
              <TableHead>{t("dunning.next")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <DunningRow key={item.invoice.id} item={item} />
            ))}
          </TableBody>
        </Table>
      )}
    </>
  );
}

type Level = "1" | "2" | "3";

function levelKey(level: number): `dunning.level.${Level}` {
  return `dunning.level.${String(level) as Level}`;
}

function DunningRow({ item }: { readonly item: DunningItem }) {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const write = useWriteReminder();
  const [confirming, setConfirming] = useState(false);
  const [mailing, setMailing] = useState<{ id: string; level: number } | null>(null);
  const invoice = item.invoice;
  const next = item.next;
  const numberId = `dunning-invoice-${invoice.id}`;
  return (
    <TableRow>
      <TableCell className="whitespace-nowrap">
        <Link
          id={numberId}
          to="/documents/$documentId"
          params={{ documentId: invoice.id }}
          className="inline-flex min-h-6 items-center font-medium text-primary underline-offset-4 hover:underline"
        >
          {invoice.number}
        </Link>
      </TableCell>
      <TableCell>{invoice.customer_name}</TableCell>
      <TableCell className="text-right whitespace-nowrap tabular-nums">
        {formatMoney(invoice.open_amount, invoice.currency, locale)}
      </TableCell>
      <TableCell className="whitespace-nowrap">
        <StatusBadge tone="overdue" label={t("dunning.days", { count: item.days_overdue })} />
      </TableCell>
      <TableCell>
        {item.reminders.length === 0 ? (
          <span className="text-muted-foreground">{t("dunning.none")}</span>
        ) : (
          <ul className="flex flex-col gap-1">
            {item.reminders.map((reminder) => (
              <li key={reminder.id} className="flex items-center gap-1">
                <a
                  href={reminderPdfUrl(reminder)}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex min-h-6 items-center gap-1 text-primary underline-offset-4 hover:underline"
                >
                  <FileTextIcon className="size-3.5" aria-hidden="true" />
                  {t(levelKey(reminder.level))}
                  <span className="text-muted-foreground">
                    {formatDate(reminder.issued_on, locale)}
                  </span>
                  <span className="sr-only">{t("common.opensInNewTab")}</span>
                </a>
                <Button
                  type="button"
                  size="icon-sm"
                  variant="ghost"
                  aria-label={`${t("mail.sendAction")}: ${t(levelKey(reminder.level))} ${invoice.number ?? ""}`}
                  onClick={() => {
                    setMailing({ id: reminder.id, level: reminder.level });
                  }}
                >
                  <MailIcon aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        )}
        <SendMailDialog
          subject={{ kind: "reminder", id: mailing?.id ?? "" }}
          title={mailing === null ? "" : t(levelKey(mailing.level))}
          open={mailing !== null}
          onOpenChange={(open) => {
            if (!open) setMailing(null);
          }}
        />
      </TableCell>
      <TableCell className="py-2">
        {next === null ? (
          <span className="text-muted-foreground">{t("dunning.done")}</span>
        ) : (
          <div className="flex flex-col items-start gap-1">
            <Button
              size="sm"
              variant={next.due ? "default" : "outline"}
              disabled={write.isPending}
              aria-describedby={numberId}
              onClick={() => {
                setConfirming(true);
              }}
            >
              <BellRingIcon aria-hidden="true" />
              {t("dunning.write", { level: t(levelKey(next.level)) })}
            </Button>
            <span className="text-xs text-muted-foreground">
              {next.due
                ? t("dunning.dueSince", { date: formatDate(next.due_on, locale) })
                : t("dunning.dueFrom", { date: formatDate(next.due_on, locale) })}
            </span>
            <AlertDialog open={confirming} onOpenChange={setConfirming}>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>
                    {t("dunning.confirmTitle", {
                      level: t(levelKey(next.level)),
                      number: invoice.number ?? "",
                    })}
                  </AlertDialogTitle>
                  <AlertDialogDescription>
                    {next.due
                      ? null
                      : `${t("dunning.confirmEarly", { date: formatDate(next.due_on, locale) })} `}
                    {t("dunning.confirmDetails", {
                      customer: invoice.customer_name,
                      deadline: formatDate(next.deadline, locale),
                      fee: formatMoney(next.fee, invoice.currency, locale),
                    })}
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() => {
                      write.mutate(
                        { invoiceId: invoice.id, level: next.level, early: !next.due },
                        {
                          onSuccess: (reminder) =>
                            toast.success(
                              t("dunning.written", { level: t(levelKey(reminder.level)) }),
                              {
                                action: {
                                  label: t("dunning.openPdf"),
                                  onClick: () => {
                                    window.open(reminderPdfUrl(reminder), "_blank", "noopener");
                                  },
                                },
                              },
                            ),
                          onError: (caught) =>
                            toast.error(errorMessage(caught) ?? t("error.generic")),
                        },
                      );
                    }}
                  >
                    {t("dunning.write", { level: t(levelKey(next.level)) })}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        )}
      </TableCell>
    </TableRow>
  );
}
