import { useI18n } from "@/components/i18n/use-i18n";
import type { Totals } from "@/features/documents/api";
import { cn } from "@/lib/cn";
import { formatMoney, formatPercent } from "@/lib/format";

interface TotalsSummaryProps {
  readonly totals: Totals;
  /** "MWST", "USt" or "VAT". */
  readonly taxName: string;
  readonly className?: string;
}

function Row({
  label,
  value,
  strong = false,
  className,
}: {
  readonly label: string;
  readonly value: string;
  readonly strong?: boolean;
  readonly className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-baseline justify-between gap-4",
        strong && "font-semibold",
        className,
      )}
    >
      <dt className={strong ? undefined : "text-muted-foreground"}>{label}</dt>
      <dd className="tabular-nums">{value}</dd>
    </div>
  );
}

/** Totals with the tax per rate, as printed on the document. */
export function TotalsSummary({ totals, taxName, className }: TotalsSummaryProps) {
  const { t, locale } = useI18n();
  const money = (amount: string) => formatMoney(amount, totals.currency, locale);
  const hasDiscount = Number(totals.discount) !== 0;
  return (
    <dl className={cn("flex flex-col gap-2 text-sm", className)}>
      <Row label={t("documents.subtotal")} value={money(totals.subtotal)} />
      {hasDiscount ? (
        <>
          <Row label={t("documents.documentDiscount")} value={money(`-${totals.discount}`)} />
          <Row label={t("documents.net")} value={money(totals.net)} />
        </>
      ) : null}
      {totals.groups.map((group) => (
        <Row
          key={`${group.vat_code}-${group.rate}`}
          label={t("documents.taxGroup", {
            tax: taxName,
            rate: formatPercent(group.rate, locale),
            amount: money(group.net),
          })}
          value={money(group.tax)}
        />
      ))}
      {Number(totals.rounding) === 0 ? null : (
        <Row label={t("documents.rounding")} value={money(totals.rounding)} />
      )}
      <Row
        label={t("documents.total")}
        value={money(totals.total)}
        strong
        className="mt-1 border-t pt-3"
      />
    </dl>
  );
}
