import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  AlarmClockIcon,
  BellRingIcon,
  FileTextIcon,
  PlusIcon,
  ReceiptIcon,
  TableIcon,
  TrendingDownIcon,
  TrendingUpIcon,
  WalletIcon,
} from "lucide-react";
import { useState, type ReactNode } from "react";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useDocumentTitle } from "@/components/use-document-title";
import { dashboardQuery, type Dashboard } from "@/features/dashboard/api";
import { ExpectedPaymentsChart, Sparkline, YearRevenueChart } from "@/features/dashboard/charts";
import {
  acceptanceRate,
  ageParts,
  dashboardCurrencies,
  recentMonths,
  yearChange,
  yearComparison,
  type AgeKey,
} from "@/features/dashboard/dashboard-model";
import { FormAlert } from "@/features/shared/form-alert";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { cn } from "@/lib/cn";
import { daysBetween, isoWeek } from "@/lib/dates";
import { formatChange, formatMoney, formatPercent, formatRelative } from "@/lib/format";

/** Latest events shown; the cards beside them stay about as tall. */
const RECENT_SHOWN = 6;

interface DashboardPageProps {
  readonly userName: string;
  /** Card below the recent activity, e.g. the backup state. */
  readonly aside?: ReactNode;
  /** Above everything else, e.g. the setup checklist of a new installation. */
  readonly top?: ReactNode;
}

export function DashboardPage({ userName, aside, top }: DashboardPageProps) {
  const { t } = useI18n();
  useDocumentTitle(t("app.pageTitle", { title: t("dashboard.title") }));
  const errorMessage = useErrorMessage();
  const query = useQuery(dashboardQuery);
  const data = query.data;
  const newInvoice = (
    <Button asChild>
      <Link to="/invoices/new">
        <PlusIcon aria-hidden="true" />
        {t("documents.newInvoice")}
      </Link>
    </Button>
  );
  return (
    <>
      <PageHeader
        title={t("dashboard.title")}
        description={t("dashboard.welcome", { name: userName })}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline">
              <Link to="/quotes/new">{t("documents.newQuote")}</Link>
            </Button>
            {newInvoice}
          </div>
        }
      />
      <FormAlert message={query.isError ? errorMessage(query.error) : null} />
      {top === undefined ? null : <div className="mb-6 empty:hidden">{top}</div>}
      {data === undefined ? (
        query.isPending ? (
          <div
            className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
            aria-busy="true"
            aria-label={t("app.loading")}
          >
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
          </div>
        ) : null
      ) : data.figures.length === 0 && data.recent.length === 0 ? (
        <div className="flex flex-col gap-6">
          <EmptyState
            icon={ReceiptIcon}
            title={t("dashboard.emptyTitle")}
            description={t("dashboard.emptyDescription")}
            action={newInvoice}
          />
          <div className="max-w-md">{aside}</div>
        </div>
      ) : (
        <Cockpit data={data} aside={aside} />
      )}
    </>
  );
}

function Cockpit({ data, aside }: { readonly data: Dashboard; readonly aside: ReactNode }) {
  const { t } = useI18n();
  const currencies = dashboardCurrencies(data);
  const [chosen, setChosen] = useState<string | null>(null);
  const currency =
    chosen !== null && currencies.includes(chosen) ? chosen : (currencies[0] ?? "CHF");
  // The installation's day: the browser may be in another time zone.
  const today = data.today;
  return (
    <div data-cockpit className="flex flex-col gap-6">
      {currencies.length > 1 ? (
        <div role="group" aria-label={t("dashboard.currency")} className="flex flex-wrap gap-1.5">
          {currencies.map((option) => (
            <Button
              key={option}
              className="max-sm:min-h-11"
              variant={option === currency ? "default" : "secondary"}
              aria-pressed={option === currency}
              onClick={() => {
                setChosen(option);
              }}
            >
              {option}
            </Button>
          ))}
        </div>
      ) : null}
      <KeyFigures data={data} currency={currency} today={today} />
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <RevenueCard data={data} currency={currency} today={today} />
        <AgingCard data={data} currency={currency} today={today} />
      </div>
      <div className="grid items-start gap-6 lg:grid-cols-2 xl:grid-cols-3">
        <TopCustomersCard data={data} currency={currency} year={today.slice(0, 4)} />
        <ExpectedCard data={data} currency={currency} />
        <div className="flex flex-col gap-6 lg:col-span-2 xl:col-span-1">
          <ActivityCard data={data} />
          {aside}
        </div>
      </div>
    </div>
  );
}

type Tone = "neutral" | "good" | "bad";

function Chip({ tone, children }: { readonly tone: Tone; readonly children: ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold whitespace-nowrap",
        tone === "good" && "bg-status-paid-bg text-status-paid-fg",
        tone === "bad" && "bg-status-overdue-bg text-status-overdue-fg",
        tone === "neutral" && "bg-muted text-muted-foreground",
      )}
    >
      {children}
    </span>
  );
}

function Tile({
  label,
  value,
  valueTone,
  chip,
  hint,
  graphic,
  trend,
  link,
}: {
  readonly label: string;
  readonly value: string;
  readonly valueTone?: "bad" | undefined;
  readonly chip: ReactNode;
  readonly hint: string;
  readonly graphic: ReactNode;
  /** A trend line below the value, across the tile. */
  readonly trend?: ReactNode;
  readonly link: ReactNode;
}) {
  return (
    <Card className="relative gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <span className="text-sm text-muted-foreground">{label}</span>
          <span
            className={cn(
              "text-2xl font-semibold tracking-tight tabular-nums",
              valueTone === "bad" && "text-status-overdue-fg",
            )}
          >
            {value}
          </span>
        </div>
        {graphic}
      </div>
      {trend}
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        {chip}
        <span>{hint}</span>
      </div>
      {link}
    </Card>
  );
}

function TileIcon({ icon: Icon, tone }: { readonly icon: typeof WalletIcon; readonly tone: Tone }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "flex size-9 shrink-0 items-center justify-center rounded-full",
        tone === "bad"
          ? "bg-status-overdue-bg text-status-overdue-fg"
          : "bg-accent text-accent-foreground",
      )}
    >
      <Icon className="size-4" />
    </span>
  );
}

/** Links in a tile cover the whole tile (the tile itself stays a plain card). */
const TILE_LINK =
  "inline-flex min-h-6 w-fit items-center text-sm text-primary max-sm:min-h-11 underline-offset-4 after:absolute after:inset-0 after:rounded-xl hover:underline";

function KeyFigures({
  data,
  currency,
  today,
}: {
  readonly data: Dashboard;
  readonly currency: string;
  readonly today: string;
}) {
  const { t, locale } = useI18n();
  const money = (amount: string) => formatMoney(amount, currency, locale);
  const figure = data.figures.find((item) => item.currency === currency);
  const quotes = data.quotes.find((item) => item.currency === currency);
  const revenue = data.year_to_date.find((item) => item.currency === currency);
  const change = revenue === undefined ? null : yearChange(revenue.current, revenue.previous);
  const unchanged = change !== null && Math.round(change * 100) === 0;
  const days = data.days_to_pay.find((item) => item.currency === currency)?.days ?? null;
  const oldestDue = data.overdue.find((invoice) => invoice.currency === currency)?.due_date ?? null;
  const rate = quotes === undefined ? null : acceptanceRate(quotes.accepted, quotes.decided);
  const year = today.slice(0, 4);
  return (
    <section
      aria-label={t("dashboard.figuresIn", { currency })}
      className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
    >
      <Tile
        label={t("dashboard.revenueYear", { year })}
        value={money(revenue?.current ?? "0.00")}
        chip={
          change === null ? (
            <Chip tone="neutral">{t("dashboard.noComparison")}</Chip>
          ) : (
            <Chip tone={unchanged ? "neutral" : change > 0 ? "good" : "bad"}>
              {unchanged ? null : change > 0 ? (
                <TrendingUpIcon className="size-3.5" aria-hidden="true" />
              ) : (
                <TrendingDownIcon className="size-3.5" aria-hidden="true" />
              )}
              {formatChange(change, locale)}
            </Chip>
          )
        }
        hint={change === null ? "" : t("dashboard.vsLastYear")}
        graphic={<TileIcon icon={TrendingUpIcon} tone="neutral" />}
        trend={<Sparkline values={recentMonths(data.revenue, currency, today)} />}
        link={
          <Link className={TILE_LINK} to="/invoices" search={{ year: Number(year) }}>
            {t("dashboard.showInvoices")}
          </Link>
        }
      />
      <Tile
        label={t("dashboard.open")}
        value={money(figure?.open ?? "0.00")}
        chip={
          <Chip tone="neutral">{t("dashboard.openCount", { count: figure?.open_count ?? 0 })}</Chip>
        }
        hint={days === null ? "" : t("dashboard.daysToPay", { count: days })}
        graphic={<TileIcon icon={WalletIcon} tone="neutral" />}
        link={
          <Link className={TILE_LINK} to="/invoices" search={{ view: "open" }}>
            {t("dashboard.showOpen")}
          </Link>
        }
      />
      <Tile
        label={t("dashboard.overdue")}
        value={money(figure?.overdue ?? "0.00")}
        valueTone={(figure?.overdue_count ?? 0) > 0 ? "bad" : undefined}
        chip={
          <Chip tone={(figure?.overdue_count ?? 0) > 0 ? "bad" : "good"}>
            {t("dashboard.overdueCount", { count: figure?.overdue_count ?? 0 })}
          </Chip>
        }
        hint={
          oldestDue === null
            ? ""
            : t("dashboard.oldestOverdue", { count: daysBetween(oldestDue, today) })
        }
        graphic={
          <TileIcon
            icon={AlarmClockIcon}
            tone={(figure?.overdue_count ?? 0) > 0 ? "bad" : "neutral"}
          />
        }
        link={
          <Link className={TILE_LINK} to="/dunning">
            {t("dashboard.showDunning")}
          </Link>
        }
      />
      <Tile
        label={t("dashboard.openQuotes")}
        value={money(quotes?.open ?? "0.00")}
        chip={
          <Chip tone="neutral">
            {t("dashboard.quoteCount", { count: quotes?.open_count ?? 0 })}
          </Chip>
        }
        hint={
          rate === null
            ? t("dashboard.noDecisions")
            : t("dashboard.acceptance", {
                rate: formatPercent(String(Math.round(rate * 100)), locale),
              })
        }
        graphic={<TileIcon icon={FileTextIcon} tone="neutral" />}
        link={
          <Link className={TILE_LINK} to="/quotes" search={{ view: "sent" }}>
            {t("dashboard.showQuotes")}
          </Link>
        }
      />
    </section>
  );
}

/** Switch a chart for the table of its numbers. */
function TableToggle({
  pressed,
  onChange,
}: {
  readonly pressed: boolean;
  readonly onChange: (pressed: boolean) => void;
}) {
  const { t } = useI18n();
  return (
    <Button
      variant="ghost"
      size="sm"
      className="max-sm:min-h-11"
      aria-pressed={pressed}
      onClick={() => {
        onChange(!pressed);
      }}
    >
      <TableIcon aria-hidden="true" />
      {t("dashboard.asTable")}
    </Button>
  );
}

function RevenueCard({
  data,
  currency,
  today,
}: {
  readonly data: Dashboard;
  readonly currency: string;
  readonly today: string;
}) {
  const { t } = useI18n();
  const [asTable, setAsTable] = useState(false);
  const comparison = yearComparison(data.revenue, currency, today);
  const year = Number(today.slice(0, 4));
  return (
    <Card aria-labelledby="revenue-title">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <CardHeader>
          <CardTitle id="revenue-title">{t("dashboard.revenue")}</CardTitle>
          <CardDescription>{t("dashboard.revenueHint", { currency })}</CardDescription>
        </CardHeader>
        <TableToggle pressed={asTable} onChange={setAsTable} />
      </div>
      <YearRevenueChart
        currency={currency}
        months={comparison.months}
        current={comparison.current}
        previous={comparison.previous}
        thisYear={year}
        lastYear={year - 1}
        asTable={asTable}
      />
    </Card>
  );
}

const AGE_COLOURS: Record<AgeKey, string> = {
  not_due: "bg-primary",
  late_30: "bg-warning",
  late_60: "bg-destructive",
  late_more: "bg-status-overdue-fg",
};

function AgingCard({
  data,
  currency,
  today,
}: {
  readonly data: Dashboard;
  readonly currency: string;
  readonly today: string;
}) {
  const { t, locale } = useI18n();
  const money = (amount: string) => formatMoney(amount, currency, locale);
  const aging = data.aging.find((item) => item.currency === currency);
  const overdue = data.overdue.filter((invoice) => invoice.currency === currency);
  const figure = data.figures.find((item) => item.currency === currency);
  return (
    <Card aria-labelledby="aging-title">
      <CardHeader className="flex-row flex-wrap items-baseline justify-between gap-2">
        <CardTitle id="aging-title">{t("dashboard.aging")}</CardTitle>
        <span className="font-semibold tabular-nums">{money(figure?.open ?? "0.00")}</span>
      </CardHeader>
      {aging === undefined ? (
        <p className="text-sm text-muted-foreground">{t("dashboard.nothingOpen")}</p>
      ) : (
        <>
          <div
            aria-hidden="true"
            className="flex h-3.5 gap-0.5 overflow-hidden rounded-full bg-muted"
          >
            {ageParts(aging)
              .filter((part) => part.share > 0)
              .map((part) => (
                <span
                  key={part.key}
                  className={cn("h-full", AGE_COLOURS[part.key])}
                  style={{ width: `${String(part.share * 100)}%` }}
                />
              ))}
          </div>
          <dl className="grid grid-cols-1 gap-x-4 gap-y-2 text-sm sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
            {ageParts(aging).map((part) => (
              <div key={part.key} className="flex items-center justify-between gap-2">
                <dt className="flex items-center gap-2 text-muted-foreground">
                  <span
                    aria-hidden="true"
                    className={cn("size-2.5 rounded-sm", AGE_COLOURS[part.key])}
                  />
                  {t(`dashboard.age.${part.key}`)}
                </dt>
                <dd className="tabular-nums">{money(part.amount)}</dd>
              </div>
            ))}
          </dl>
        </>
      )}
      <h3 className="text-sm font-semibold">{t("dashboard.overdueList")}</h3>
      {overdue.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("dashboard.noOverdue")}</p>
      ) : (
        <ul className="flex flex-col divide-y text-sm">
          {overdue.map((invoice) => (
            <li key={invoice.id} className="flex items-center justify-between gap-3 py-2">
              <div className="flex min-w-0 flex-col">
                <Link
                  to="/documents/$documentId"
                  params={{ documentId: invoice.id }}
                  className="inline-flex min-h-6 items-center truncate font-medium underline-offset-4 hover:underline"
                >
                  {invoice.customer_name}
                </Link>
                <span className="text-xs text-muted-foreground">
                  {invoice.number} ·{" "}
                  {t("dashboard.daysLate", {
                    count: invoice.due_date === null ? 0 : daysBetween(invoice.due_date, today),
                  })}
                </span>
              </div>
              <span className="shrink-0 tabular-nums">{money(invoice.open_amount)}</span>
            </li>
          ))}
        </ul>
      )}
      {overdue.length === 0 ? null : (
        <Button asChild size="sm" variant="secondary" className="w-fit">
          <Link to="/dunning">
            <BellRingIcon aria-hidden="true" />
            {t("dashboard.remind")}
          </Link>
        </Button>
      )}
    </Card>
  );
}

function TopCustomersCard({
  data,
  currency,
  year,
}: {
  readonly data: Dashboard;
  readonly currency: string;
  readonly year: string;
}) {
  const { t, locale } = useI18n();
  const customers = data.top_customers.filter((entry) => entry.currency === currency);
  const best = Math.max(1, ...customers.map((entry) => Number(entry.net)));
  return (
    <Card aria-labelledby="customers-title">
      <CardHeader>
        <CardTitle id="customers-title">{t("dashboard.topCustomers", { year })}</CardTitle>
        <CardDescription>{t("dashboard.topCustomersHint")}</CardDescription>
      </CardHeader>
      {customers.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("dashboard.noCustomerRevenue")}</p>
      ) : (
        <ol className="flex flex-col gap-3 text-sm">
          {customers.map((entry) => (
            <li key={entry.customer_id} className="flex flex-col gap-1.5">
              <div className="flex items-baseline justify-between gap-3">
                <Link
                  to="/customers/$customerId"
                  params={{ customerId: entry.customer_id }}
                  className="inline-flex min-h-6 min-w-0 items-center truncate underline-offset-4 hover:underline"
                >
                  {entry.customer_name}
                </Link>
                <span className="shrink-0 tabular-nums">
                  {formatMoney(entry.net, currency, locale)}
                </span>
              </div>
              <div aria-hidden="true" className="h-2 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${String((Number(entry.net) / best) * 100)}%` }}
                />
              </div>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

function ExpectedCard({ data, currency }: { readonly data: Dashboard; readonly currency: string }) {
  const { t } = useI18n();
  const [asTable, setAsTable] = useState(false);
  const weeks = data.expected
    .filter((week) => week.currency === currency)
    .map((week) => ({
      label: t("dashboard.weekLabel", { week: isoWeek(week.week_start) }),
      amount: week.amount,
    }));
  return (
    <Card aria-labelledby="expected-title">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <CardHeader>
          <CardTitle id="expected-title">{t("dashboard.expected")}</CardTitle>
          <CardDescription>{t("dashboard.expectedHint")}</CardDescription>
        </CardHeader>
        {weeks.length === 0 ? null : <TableToggle pressed={asTable} onChange={setAsTable} />}
      </div>
      {weeks.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("dashboard.nothingOpen")}</p>
      ) : (
        <ExpectedPaymentsChart currency={currency} weeks={weeks} asTable={asTable} />
      )}
    </Card>
  );
}

function ActivityCard({ data }: { readonly data: Dashboard }) {
  const { t, locale } = useI18n();
  const now = new Date();
  return (
    <Card aria-labelledby="activity-title">
      <CardHeader>
        <CardTitle id="activity-title">{t("dashboard.activity")}</CardTitle>
      </CardHeader>
      {data.recent.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("dashboard.noActivity")}</p>
      ) : (
        <ol className="flex flex-col divide-y">
          {data.recent.slice(0, RECENT_SHOWN).map((activity, index) => (
            <li
              key={`${activity.document.id}-${activity.at}-${String(index)}`}
              className="relative flex items-center justify-between gap-3 py-2 text-sm"
            >
              <div className="flex min-w-0 flex-col">
                <Link
                  to="/documents/$documentId"
                  params={{ documentId: activity.document.id }}
                  className="inline-flex min-h-6 items-center font-medium underline-offset-4 after:absolute after:inset-0 hover:underline"
                >
                  {t(`event.${activity.event}`)}: {t(`documentType.${activity.document.type}`)}{" "}
                  {activity.document.number ?? ""}
                </Link>
                <span className="text-muted-foreground">
                  {activity.document.customer_name} ·{" "}
                  <time dateTime={activity.at}>
                    {formatRelative(new Date(activity.at), now, locale)}
                  </time>
                </span>
              </div>
              <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                {formatMoney(activity.document.total, activity.document.currency, locale)}
              </span>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
