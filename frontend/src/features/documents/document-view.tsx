import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { FileTextIcon, MailIcon, Trash2Icon } from "lucide-react";
import { useState } from "react";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { remindersQuery, type DocumentDetail } from "@/features/documents/api";
import { EInvoiceCard } from "@/features/documents/e-invoice-card";
import { TotalsSummary } from "@/features/documents/totals-summary";
import { SendMailDialog } from "@/features/shared/send-mail-dialog";
import { formatDate, formatDateTime, formatMoney, formatNumber, formatPercent } from "@/lib/format";

interface DocumentViewProps {
  readonly document: DocumentDetail;
  readonly taxName: string;
  readonly onRemovePayment?: ((paymentId: string) => void) | undefined;
}

function Meta({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm font-medium tabular-nums">{value}</dd>
    </div>
  );
}

/** Read-only view of an issued document: content and totals are frozen. */
export function DocumentView({ document, taxName, onRemovePayment }: DocumentViewProps) {
  const { t, locale } = useI18n();
  const money = (amount: string, digits = 2) =>
    formatMoney(amount, document.currency, locale, digits);
  const date = (value: string | null) =>
    value === null ? t("common.none") : formatDate(value, locale);
  const recipient = document.recipient;
  const isInvoice = document.type !== "quote";

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="flex min-w-0 flex-col gap-6">
        <Card aria-labelledby="document-facts">
          <h2 id="document-facts" className="sr-only">
            {t("documents.facts")}
          </h2>
          <div className="grid gap-6 sm:grid-cols-2">
            {recipient === null ? null : (
              <address className="flex flex-col text-sm not-italic">
                <span className="text-xs text-muted-foreground">{t("documents.customer")}</span>
                <Link
                  to="/customers/$customerId"
                  params={{ customerId: document.customer_id }}
                  className="inline-flex min-h-6 w-fit items-center font-medium underline-offset-4 hover:underline"
                >
                  {recipient.name}
                </Link>
                {recipient.contact_person === "" ? null : <span>{recipient.contact_person}</span>}
                <span>
                  {recipient.address.street} {recipient.address.house_number}
                </span>
                <span>
                  {recipient.address.postal_code} {recipient.address.city}
                </span>
                {recipient.vat_number === null ? null : (
                  <span className="text-muted-foreground">{recipient.vat_number}</span>
                )}
              </address>
            )}
            <dl className="grid grid-cols-2 gap-4">
              <Meta label={t("documents.issueDate")} value={date(document.issue_date)} />
              <Meta
                label={isInvoice ? t("documents.dueDate") : t("documents.validUntil")}
                value={date(document.due_date)}
              />
              {document.service_from === null && document.service_to === null ? null : (
                <Meta
                  label={t("documents.servicePeriod")}
                  value={`${date(document.service_from)} – ${date(document.service_to)}`}
                />
              )}
              {document.reference === "" ? null : (
                <Meta label={t("documents.reference")} value={document.reference} />
              )}
              <Meta label={t("documents.treatment")} value={t(`treatment.${document.treatment}`)} />
            </dl>
          </div>
          {document.subject === "" ? null : <p className="font-medium">{document.subject}</p>}
          {document.intro_text === "" ? null : (
            <p className="text-sm whitespace-pre-line">{document.intro_text}</p>
          )}
        </Card>

        <Card aria-labelledby="document-lines">
          <CardHeader>
            <CardTitle id="document-lines">{t("documents.sectionLines")}</CardTitle>
          </CardHeader>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("documents.lineDescription")}</TableHead>
                <TableHead className="text-right">{t("documents.lineQuantity")}</TableHead>
                <TableHead className="hidden text-right md:table-cell">
                  {t("documents.linePrice")}
                </TableHead>
                <TableHead className="hidden text-right lg:table-cell">
                  {t("documents.lineTaxRate", { tax: taxName })}
                </TableHead>
                <TableHead className="text-right">{t("documents.lineAmount")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {document.lines.map((line) =>
                line.kind === "text" ? (
                  <TableRow key={line.id}>
                    <TableCell colSpan={5} className="whitespace-pre-line">
                      <span className="font-medium">{line.description}</span>
                      {line.details === "" ? null : (
                        <span className="block text-muted-foreground">{line.details}</span>
                      )}
                    </TableCell>
                  </TableRow>
                ) : (
                  <TableRow key={line.id}>
                    <TableCell className="whitespace-pre-line">
                      <span className="font-medium">{line.description}</span>
                      {line.details === "" ? null : (
                        <span className="block text-muted-foreground">{line.details}</span>
                      )}
                      {Number(line.discount_percent) === 0 ? null : (
                        <span className="block text-xs text-muted-foreground">
                          {t("documents.lineDiscountApplied", {
                            percent: formatPercent(line.discount_percent, locale),
                          })}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatNumber(line.quantity, locale, 4)} {line.unit ?? ""}
                    </TableCell>
                    <TableCell className="hidden text-right tabular-nums md:table-cell">
                      {money(line.unit_price, 4)}
                    </TableCell>
                    <TableCell className="hidden text-right tabular-nums lg:table-cell">
                      {line.tax_rate === null
                        ? t("common.none")
                        : formatPercent(line.tax_rate, locale)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {line.amount === null ? t("common.none") : money(line.amount)}
                    </TableCell>
                  </TableRow>
                ),
              )}
            </TableBody>
          </Table>
          {document.closing_text === "" ? null : (
            <p className="text-sm whitespace-pre-line">{document.closing_text}</p>
          )}
        </Card>
      </div>

      <aside className="flex flex-col gap-6 xl:sticky xl:top-20 xl:self-start">
        <Card aria-labelledby="document-totals">
          <CardHeader>
            <CardTitle id="document-totals">{t("documents.totals")}</CardTitle>
          </CardHeader>
          <TotalsSummary totals={document.totals} taxName={taxName} />
          {isInvoice && document.type === "invoice" ? (
            <dl className="flex flex-col gap-2 border-t pt-3 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">{t("documents.paid")}</dt>
                <dd className="tabular-nums">{money(document.paid_amount)}</dd>
              </div>
              <div className="flex justify-between gap-4 font-semibold">
                <dt>{t("documents.openAmount")}</dt>
                <dd className="tabular-nums">{money(document.open_amount)}</dd>
              </div>
            </dl>
          ) : null}
        </Card>

        {document.payments.length === 0 ? null : (
          <Card aria-labelledby="document-payments">
            <CardHeader>
              <CardTitle id="document-payments">{t("documents.payments")}</CardTitle>
            </CardHeader>
            <ul className="flex flex-col divide-y text-sm">
              {document.payments.map((payment) => (
                <li key={payment.id} className="flex items-center justify-between gap-2 py-2">
                  <div className="flex flex-col">
                    <span className="font-medium tabular-nums">{money(payment.amount)}</span>
                    <span className="text-xs text-muted-foreground">
                      {formatDate(payment.paid_on, locale)}
                      {payment.note === "" ? "" : ` · ${payment.note}`}
                    </span>
                  </div>
                  {onRemovePayment === undefined ? null : (
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => {
                        onRemovePayment(payment.id);
                      }}
                      aria-label={t("documents.removePayment", {
                        amount: money(payment.amount),
                        date: formatDate(payment.paid_on, locale),
                      })}
                    >
                      <Trash2Icon aria-hidden="true" />
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </Card>
        )}

        {document.type !== "quote" && document.status !== "draft" ? (
          <EInvoiceCard documentId={document.id} />
        ) : null}

        {document.type === "invoice" && document.status !== "draft" ? (
          <DocumentReminders
            documentId={document.id}
            open={document.status === "issued" || document.status === "partially_paid"}
          />
        ) : null}

        <DocumentHistory document={document} />
      </aside>
    </div>
  );
}

/** Payment reminders written for an invoice, as PDF; nothing while there are none. */
function DocumentReminders({
  documentId,
  open,
}: {
  readonly documentId: string;
  /** Reminders of paid or cancelled invoices are only shown, not sent any more. */
  readonly open: boolean;
}) {
  const { t, locale } = useI18n();
  const reminders = useQuery(remindersQuery(documentId)).data ?? [];
  const [mailing, setMailing] = useState<{ id: string; title: string } | null>(null);
  if (reminders.length === 0) return null;
  return (
    <Card aria-labelledby="document-reminders">
      <CardHeader>
        <CardTitle id="document-reminders">{t("documents.reminders")}</CardTitle>
      </CardHeader>
      <ul className="flex flex-col gap-1 text-sm">
        {reminders.map((reminder) => (
          <li key={reminder.id} className="flex flex-wrap items-center justify-between gap-2">
            <a
              href={`/api/reminders/${reminder.id}/pdf`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex min-h-6 items-center gap-1 text-primary underline-offset-4 hover:underline"
            >
              <FileTextIcon className="size-3.5" aria-hidden="true" />
              {t(`dunning.level.${String(reminder.level) as "1" | "2" | "3"}`)}
              <span className="text-muted-foreground">
                {formatDate(reminder.issued_on, locale)}
              </span>
              <span className="sr-only">{t("common.opensInNewTab")}</span>
            </a>
            {open ? (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  setMailing({
                    id: reminder.id,
                    title: t(`dunning.level.${String(reminder.level) as "1" | "2" | "3"}`),
                  });
                }}
              >
                <MailIcon aria-hidden="true" />
                {t("mail.sendAction")}
                <span className="sr-only">
                  {t(`dunning.level.${String(reminder.level) as "1" | "2" | "3"}`)}
                </span>
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
      <SendMailDialog
        subject={{ kind: "reminder", id: mailing?.id ?? "" }}
        title={mailing?.title ?? ""}
        open={mailing !== null}
        onOpenChange={(open) => {
          if (!open) setMailing(null);
        }}
      />
    </Card>
  );
}

/** Event log of the document (who did what when is the audit trail of GoBD / OR 958f). */
export function DocumentHistory({ document }: { readonly document: DocumentDetail }) {
  const { t, locale } = useI18n();
  return (
    <Card aria-labelledby="document-history">
      <CardHeader>
        <CardTitle id="document-history">{t("documents.history")}</CardTitle>
      </CardHeader>
      <ol className="flex flex-col gap-3 border-l pl-4 text-sm">
        {[...document.events].reverse().map((event, index) => (
          <li key={`${event.at}-${String(index)}`} className="flex flex-col">
            <span className="font-medium">{t(`event.${event.kind}`)}</span>
            <EventDetail kind={event.kind} detail={event.detail} currency={document.currency} />
            <time dateTime={event.at} className="text-xs text-muted-foreground">
              {formatDateTime(event.at, locale)}
            </time>
          </li>
        ))}
      </ol>
    </Card>
  );
}

const REMINDER_LEVELS = ["1", "2", "3"] as const;

function isReminderLevel(detail: string): detail is (typeof REMINDER_LEVELS)[number] {
  return (REMINDER_LEVELS as readonly string[]).includes(detail);
}
const REMINDER_MAIL = /^([123]) (.*)$/s;
const TREATMENT_DETAIL = /^(domestic|reverse_charge|export|small_business|exempt)(?:: (.*))?$/s;

function EventDetail({
  kind,
  detail,
  currency,
}: {
  readonly kind: DocumentDetail["events"][number]["kind"];
  readonly detail: string;
  readonly currency: string;
}) {
  const { t, locale } = useI18n();
  // The converted invoice is linked above the document (it may be deleted again).
  if (detail === "" || kind === "converted") return null;
  if (kind === "payment_added" || kind === "payment_removed") {
    return (
      <span className="text-muted-foreground tabular-nums">
        {formatMoney(detail, currency, locale)}
      </span>
    );
  }
  if (kind === "reminded" && isReminderLevel(detail)) {
    return <span className="text-muted-foreground">{t(`dunning.level.${detail}`)}</span>;
  }
  const mailed = kind === "reminder_emailed" ? REMINDER_MAIL.exec(detail) : null;
  if (mailed !== null && isReminderLevel(mailed[1] ?? "")) {
    const level = t(`dunning.level.${mailed[1] as (typeof REMINDER_LEVELS)[number]}`);
    return <span className="text-muted-foreground">{`${level} · ${mailed[2] ?? ""}`}</span>;
  }
  const treatment = kind === "tax_overridden" ? TREATMENT_DETAIL.exec(detail) : null;
  if (treatment !== null) {
    const name = t(`treatment.${treatment[1] as TreatmentKey}`);
    const reason = treatment[2];
    return (
      <span className="text-muted-foreground">
        {reason === undefined ? name : `${name}: ${reason}`}
      </span>
    );
  }
  return <span className="text-muted-foreground">{detail}</span>;
}

type TreatmentKey = DocumentDetail["treatment"];
